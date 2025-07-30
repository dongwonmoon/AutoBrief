import os
import shutil
import pika
import json
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from psycopg2.extensions import connection
from pydantic import BaseModel
import qdrant_client
from langchain_community.vectorstores import Qdrant
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.prompts import PromptTemplate


from core.settings import config
from core.db import get_db
from core.crud import crud_project_group

router = APIRouter()

llm = ChatOpenAI(model_name="gpt-4o")
embeddings = OpenAIEmbeddings()
DATA_DIR = config["data"]["data_dir"]


class ChatRequest(BaseModel):
    query: str


@router.get("/project-groups")
def get_project_groups_endpoint():
    if not os.path.isdir(DATA_DIR):
        raise HTTPException(
            status_code=500, detail=f"Data directory not found at {DATA_DIR}"
        )
    try:
        groups = [
            name
            for name in os.listdir(DATA_DIR)
            if os.path.isdir(os.path.join(DATA_DIR, name))
        ]
        return {"project_groups": groups}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to read directory: {str(e)}"
        )


@router.post("/project-group/add")
def add_project_group_endpoint(group_name: str, conn: connection = Depends(get_db)):
    if not group_name:
        raise HTTPException(status_code=400, detail="Group name is required")
    existing_group = crud_project_group.get_project_group_by_name(conn, group_name)
    if existing_group:
        raise HTTPException(status_code=400, detail="Group already exists")

    try:
        new_group = crud_project_group.create_project_group(conn, group_name)
        if not new_group:
            raise HTTPException(
                status_code=500, detail="Failed to create group directory"
            )
        return {"message": f"Project group '{group_name}' created successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create group: {str(e)}")


@router.post("/project-group/delete")
def delete_project_group_endpoint(group_name: str, conn: connection = Depends(get_db)):
    if not group_name:
        raise HTTPException(status_code=400, detail="Group name is required")

    try:
        success = crud_project_group.delete_project_group(conn, group_name)
        if not success:
            raise HTTPException(status_code=404, detail="Group not found")
        return {"message": f"Project group '{group_name}' deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete group: {str(e)}")


@router.get("/{group_name}/mindmap")
def get_mindmap_data(group_name: str, conn: connection = Depends(get_db)):
    """
    생성된 마인드맵 데이터를 JSON 파일에서 읽어 반환합니다.
    """
    if not group_name:
        raise HTTPException(status_code=400, detail="Group name is required")

    try:
        mindmap_data = crud_project_group.get_mindmap(conn, group_name)
        print(mindmap_data)
        if mindmap_data is None or mindmap_data[0] is None:
            raise HTTPException(status_code=404, detail="Mindmap data not found for this group.")
        return {"mindmap_data": mindmap_data[0]}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load mindmap from group: {str(e)}"
        )


@router.post("/{group_name}/upload")
async def upload_document(
    group_name: str, file: UploadFile = File(...), conn: connection = Depends(get_db)
):
    """
    지정된 프로젝트 그룹에 문서를 업로드하고, RabbitMQ에 메세지를 전송합니다.
    """
    cur = conn.cursor()
    group_path = os.path.join(DATA_DIR, group_name)
    if not os.path.exists(group_path):
        raise HTTPException(status_code=404, detail="Project group not found")

    file_path = os.path.join(group_path, file.filename)

    try:
        sql = "SELECT id FROM project_groups WHERE group_name = %s"
        cur.execute(sql, (group_name,))
        group_id = cur.fetchone()
        print(group_id)
        sql = "INSERT INTO documents (group_id, file_name) VALUES (%s, %s)"
        cur.execute(sql, (group_id[0], file.filename))
        conn.commit()

        print(f"✅ Document '{file.filename} saved to database.")

        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=os.getenv("RABBITMQ_HOST", "rabbitmq"))
        )
        channel = connection.channel()

        channel.queue_declare(queue="document_queue", durable=True)
        message = {
            "project_group": group_name,
            "file_name": file.filename,
        }

        channel.basic_publish(
            exchange="",
            routing_key="document_queue",
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
            ),
        )

        connection.close()
        print(f"✅ Message sent to RabbitMQ for file: {file.filename}")

        return {
            "message": "File uploaded and processing job queued.",
            "filename": file.filename,
        }
    except Exception as e:
        print(f"❌ Error uploading file: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
    finally:
        cur.close()
        file.file.close()


@router.post("/{group_name}/chat")
async def chat_with_documents(group_name: str, request: ChatRequest):
    try:
        client = qdrant_client.QdrantClient(host="qdrant", port=6333)
        qdrant = Qdrant(
            client=client, collection_name=group_name, embeddings=embeddings
        )
        retriever = qdrant.as_retriever()
        retrieved_docs = retriever.invoke(request.query)

        # 문서 형식으로 변환
        sources = [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
            }
            for doc in retrieved_docs
        ]

        context_string = "\n\n---\n\n".join(
            [doc.page_content for doc in retrieved_docs]
        )

        # 프롬프트 정의
        prompt_template = """
        사용자는 자신이 관심있어하는 문서들을 당신에게 제공했습니다. 당신은 사용자가 제공한 문서들을 사용하여 질문에 답변할 수 있는 AI 어시스턴트입니다.

        문서:
        {context}

        질문: {question}

        답변:
        """

        PROMPT = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )

        # 최종 프롬프트를 완성합니다.
        final_prompt = PROMPT.format(context=context_string, question=request.query)

        # LLM 호출
        response = llm.invoke(final_prompt)
        answer = response.content.strip()

        return {"answer": answer, "sources": sources}

    except Exception as e:
        print(f"An unexpected error occurred in chat API: {e}")
        raise HTTPException(status_code=500, detail="An error occurred.")


@router.get("/{group_name}/summaries", response_model=dict)
def get_all_summaries(group_name: str, conn: connection = Depends(get_db)):
    """
    특정 프로젝트 그룹에 속한 모든 문서의 요약 정보를 가져옵니다.
    """
    cur = conn.cursor()
    group_path = os.path.join(DATA_DIR, group_name)
    if not os.path.exists(group_path):
        raise HTTPException(status_code=404, detail="Project group not found")

    summaries = crud_project_group.get_summaries(conn, group_name)
    if not summaries:
        return {"summaries": []}

    formatted_summaries = [{"file_name": s[0], "summary": s[1]} for s in summaries]
    return {"summaries": formatted_summaries}

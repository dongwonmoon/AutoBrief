import os
import json
from langchain_unstructured import UnstructuredLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Qdrant
from pydantic import BaseModel, Field
from typing import List, Optional
from psycopg2.extras import RealDictCursor

from core.settings import config

openai_client = ChatOpenAI(model="gpt-3.5-turbo")
embeddings = OpenAIEmbeddings()


class MindMapNode(BaseModel):
    topic: str = Field(..., description="이 노드의 핵심 주제 또는 요약 내용")
    children: Optional[List["MindMapNode"]] = Field(
        None, description="이 주제와 관련된 하위 주제 노드들의 리스트"
    )


class MindMapTool(BaseModel):
    mindmap: MindMapNode = Field(
        ..., description="생성된 마인드맵의 최상위 루트 노드입니다."
    )


class DocumentProcessor:
    def __init__(self, db_connection):
        self.conn = db_connection

    def process_for_rag(self, file_path: str, project_group: str):
        """
        Unstructured를 사용하여 문서를 처리하고 Qdrant에 저장합니다.
        """
        print(f"[RAG] Processing started for {file_path}")
        loader = UnstructuredLoader(file_path, mode="elements")
        documents = loader.load()
        full_text = "\n\n".join([d.page_content for d in documents])

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n"],
        )
        split_docs = text_splitter.split_text(full_text)

        Qdrant.from_texts(
            split_docs,
            embeddings,
            host="qdrant",
            port=6333,
            collection_name=project_group,
        )
        print(
            f"[RAG] Successfully stored {len(split_docs)} chunks in Qdrant collection: {project_group}"
        )

    def process_for_summary(self, file_path: str, project_group: str):
        """
        문서의 요약을 생성하고 데이터베이스에 저장합니다.
        """
        print(f"[Summary] Processing started for {file_path}")
        loader = UnstructuredLoader(file_path, mode="elements")
        documents = loader.load()
        full_text = "\n\n".join([d.page_content for d in documents])

        summary = openai_client.invoke(
            [
                {
                    "role": "system",
                    "content": "당신은 요약에 능숙한 AI입니다. 짧은 문서라면, 구체적인 요약을 생성하고, 긴 문서라면 대략적인 요약을 수행합니다.",
                },
                {"role": "user", "content": f"다음 문서를 요약해줘.\n\n{full_text}"},
            ]
        )
        summary_text = summary.content.strip()
        print(f"[Summary] Generated summary for {file_path}")
        print(f"[Summary] Summary: {summary_text}")

        cur = self.conn.cursor()
        file_name = os.path.basename(file_path)

        try:
            sql = "SELECT id FROM project_groups WHERE group_name = %s"
            cur.execute(sql, (project_group,))
            group_id = cur.fetchone()

            sql = "SELECT id FROM summaries WHERE group_id = %s AND file_name = %s"
            cur.execute(sql, (group_id[0], file_name))
            if cur.fetchone():
                id = cur.fetchone()

            sql = """
                   INSERT INTO summaries (group_id, file_name, summary) 
                   VALUES (%s, %s, %s)
                   """
            cur.execute(sql, (group_id[0], file_name, summary_text))
            self.conn.commit()

            print(f"✅ Summary of '{file_name}' saved to database.")

        except Exception as e:
            print(f"❌ Error Summaring file: {e}")
            self.conn.rollback()
        finally:
            cur.close()

    def process_for_mindmap(self, project_group: str, new_document_text: str):
        """
        프로젝트 그룹의 마인드맵을 생성하거나 업데이트합니다.
        """
        print(f"[Mindmap] Processing started for project group: {project_group}")
        cur = self.conn.cursor(cursor_factory=RealDictCursor)

        try:
            sql = "SELECT id FROM project_groups WHERE group_name = %s"
            cur.execute(sql, (project_group,))
            group_id_result = cur.fetchone()
            if not group_id_result:
                print(f"❌ Group '{project_group}' not found in database.")
                return
            group_id = group_id_result["id"]

            sql = "SELECT mindmap_data FROM mindmaps WHERE group_id = %s"
            cur.execute(sql, (group_id,))
            existing_mindmap_result = cur.fetchone()
            existing_mindmap_json = (
                existing_mindmap_result["mindmap_data"]
                if existing_mindmap_result
                else None
            )

            if existing_mindmap_json:
                prompt = f"""
                기존 마인드맵:
                {json.dumps(existing_mindmap_json, ensure_ascii=False, indent=2)}

                새로운 문서 내용:
                {new_document_text}

                위의 '기존 마인드맵'에 '새로운 문서 내용'을 통합하여 확장된 마인드맵을 JSON 형식으로 생성해줘.
                기존의 구조를 최대한 유지하면서, 새로운 내용을 적절한 위치에 추가하거나 새로운 가지를 만들어줘.
                """
                print("[Mindmap] Merging with existing mindmap.")
            else:
                prompt = f"""
                다음 내용을 바탕으로 상세한 마인드맵을 JSON 형식으로 생성해줘:
                {new_document_text}
                """
                print("[Mindmap] Creating new mindmap.")

            mindmap_response = openai_client.invoke(
                [
                    {
                        "role": "system",
                        "content": "당신은 주어진 내용을 분석하여 체계적인 마인드맵을 JSON 형식으로 만드는 전문가입니다.",
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "create_mindmap",
                            "description": "Creates a mindmap.",
                            "parameters": MindMapTool.model_json_schema(),
                        },
                    }
                ],
                tool_choice={
                    "type": "function",
                    "function": {"name": "create_mindmap"},
                },
            )

            tool_args = mindmap_response.tool_calls[0]["args"]
            new_mindmap_data = MindMapTool(**tool_args).model_dump_json()

            if existing_mindmap_json:
                sql = "UPDATE mindmaps SET mindmap_data = %s WHERE group_id = %s"
                cur.execute(sql, (new_mindmap_data, group_id))
                print(
                    f"[Mindmap] Successfully updated mindmap for group_id: {group_id}"
                )
            else:
                sql = "INSERT INTO mindmaps (group_id, mindmap_data) VALUES (%s, %s)"
                cur.execute(sql, (group_id, new_mindmap_data))
                print(
                    f"[Mindmap] Successfully created new mindmap for group_id: {group_id}"
                )

            self.conn.commit()

        except Exception as e:
            print(f"❌ Error processing mindmap for group {project_group}: {e}")
            self.conn.rollback()
        finally:
            cur.close()

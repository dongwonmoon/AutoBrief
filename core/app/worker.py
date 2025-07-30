import os
import pika
import json
from langchain_unstructured import UnstructuredLoader

from core.settings import config
from core.db import get_db
from core.services.document_processor import DocumentProcessor

DATA_DIR = config["data"]["data_dir"]
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")

def callback(ch, method, properties, body):
    """메시지 수신 시 실행될 메인 콜백 함수"""
    print("\n[Worker] ✅ Received message from RabbitMQ")
    document_data = json.loads(body)
    file_name = document_data.get("file_name")
    project_group = document_data.get("project_group")
    file_path = os.path.join(DATA_DIR, project_group, file_name)

    db_gen = get_db()
    conn = next(db_gen)

    try:
        processor = DocumentProcessor(conn)

        loader = UnstructuredLoader(file_path, mode="elements")
        documents = loader.load()
        full_text = "\n\n".join([d.page_content for d in documents])

        processor.process_for_rag(file_path, project_group)
        processor.process_for_summary(file_path, project_group)
        processor.process_for_mindmap(project_group, full_text)

        print(f"[Worker] ✅ Successfully processed file: {file_path}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"[Worker] ❌ Error processing {file_path}: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    finally:
        if conn:
            conn.close()

def main():
    """RabbitMQ 연결 및 소비 시작"""
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST, heartbeat=600, blocked_connection_timeout=300
        )
    )
    channel = connection.channel()
    channel.queue_declare(queue="document_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="document_queue", on_message_callback=callback)
    print("✅ RabbitMQ Worker is waiting for messages...")
    channel.start_consuming()

if __name__ == "__main__":
    main()
import os
from psycopg2.extensions import connection

from core.settings import config

DATA_DIR = config["data"]["data_dir"]


def get_project_group_by_name(conn: connection, group_name: str):
    """이름으로 프로젝트 그룹을 조회합니다."""
    cur = conn.cursor()
    try:
        sql = "SELECT id, group_name FROM project_groups WHERE group_name = %s"
        cur.execute(sql, (group_name,))
        return cur.fetchone()
    finally:
        cur.close()


def create_project_group(conn: connection, group_name: str):
    """새로운 프로젝트 그룹을 생성합니다."""
    group_path = os.path.join(DATA_DIR, group_name)
    if os.path.exists(group_path):
        return None  # 이미 존재하는 경우

    cur = conn.cursor()
    try:
        sql = "INSERT INTO project_groups (group_name) VALUES (%s) RETURNING id"
        cur.execute(sql, (group_name,))
        new_group_id = cur.fetchone()[0]
        conn.commit()
        os.makedirs(group_path)
        return {"id": new_group_id, "group_name": group_name}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()


def delete_project_group(conn: connection, group_name: str):
    """프로젝트 그룹을 삭제합니다."""
    group_path = os.path.join(DATA_DIR, group_name)
    if not os.path.exists(group_path):
        return False  # 존재하지 않는 경우

    cur = conn.cursor()
    try:
        import shutil

        sql = "DELETE FROM project_groups WHERE group_name = %s"
        cur.execute(sql, (group_name,))
        conn.commit()
        shutil.rmtree(group_path)
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()


def get_mindmap(conn: connection, group_name: str):
    """프로젝트 그룹의 마인드맵 데이터를 조회합니다."""
    cur = conn.cursor()
    try:
        sql = "SELECT id FROM project_groups WHERE group_name = %s"
        cur.execute(sql, (group_name,))
        group_id_result = cur.fetchone()

        if group_id_result:
            group_id = group_id_result[0]
            sql = "SELECT mindmap_data FROM mindmaps WHERE group_id = %s"
            cur.execute(sql, (group_id,))
            return cur.fetchone()
        return None
    finally:
        cur.close()


def get_summaries(conn: connection, group_name: str):
    """프로젝트 그룹의 요약 데이터를 조회합니다."""
    cur = conn.cursor()
    try:
        sql = "SELECT id FROM project_groups WHERE group_name = %s"
        cur.execute(sql, (group_name,))
        group_id_result = cur.fetchone()

        if group_id_result:
            group_id = group_id_result[0]
            sql = "SELECT file_name, summary FROM summaries WHERE group_id = %s"
            cur.execute(sql, (group_id,))
            return cur.fetchall()
        return []
    finally:
        cur.close()

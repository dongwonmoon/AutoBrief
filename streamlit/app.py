import streamlit as st
import requests
import json
from streamlit_agraph import agraph, Node, Edge, Config

# --- Configuration ---
# Docker 환경에서는 'http://backend:8000/api/v1' 을 사용합니다.
# 로컬에서 직접 실행할 때는 'http://localhost:8000/api/v1' 로 변경하세요.
BACKEND_URL = "http://backend:8000/api/v1"

# --- API Helper Functions ---


def get_project_groups():
    """백엔드에서 모든 프로젝트 그룹 목록을 가져옵니다."""
    try:
        response = requests.get(f"{BACKEND_URL}/project-groups")
        response.raise_for_status()
        return response.json().get("project_groups", [])
    except requests.exceptions.RequestException as e:
        st.error(f"그룹 목록을 불러오는 데 실패했습니다: {e}")
        return []


def add_project_group(group_name):
    """새로운 프로젝트 그룹을 생성합니다."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/project-group/add", params={"group_name": group_name}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(
            f"그룹 생성 실패: {e.response.json().get('detail') if e.response else e}"
        )
        return None


def delete_project_group(group_name):
    """프로젝트 그룹을 삭제합니다."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/project-group/delete", params={"group_name": group_name}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(
            f"그룹 삭제 실패: {e.response.json().get('detail') if e.response else e}"
        )
        return None


def upload_document(group_name, uploaded_file):
    """선택된 그룹에 문서를 업로드합니다."""
    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
    try:
        response = requests.post(f"{BACKEND_URL}/{group_name}/upload", files=files)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(
            f"파일 업로드 실패: {e.response.json().get('detail') if e.response else e}"
        )
        return None


def get_mindmap(group_name):
    """그룹의 마인드맵 데이터를 가져옵니다."""
    try:
        response = requests.get(f"{BACKEND_URL}/{group_name}/mindmap")
        response.raise_for_status()
        # API 응답이 리스트 안에 튜플 형태일 수 있으므로 파싱
        mindmap_tuple = response.json().get("mindmap_data", [])
        if mindmap_tuple:
            return mindmap_tuple
        return None
    except requests.exceptions.RequestException as e:
        st.error(
            f"마인드맵 로딩 실패: {e.response.json().get('detail') if e.response else e}"
        )
        return None


def get_summaries(group_name):
    """백엔드에서 요약 목록을 가져오는 새로운 함수"""
    try:
        response = requests.get(f"{BACKEND_URL}/{group_name}/summaries")
        response.raise_for_status()
        return response.json().get("summaries", [])
    except requests.exceptions.RequestException:
        return []  # 요약이 없는 것은 정상이므로 오류 메시지 없이 빈 리스트 반환


def post_chat(group_name, query):
    """채팅 메시지를 보내고 답변을 받습니다."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/{group_name}/chat", json={"query": query}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(
            f"채팅 응답 실패: {e.response.json().get('detail') if e.response else e}"
        )
        return None


def build_mindmap_graph(mindmap_data):
    """마인드맵 JSON을 agraph가 이해하는 노드와 엣지로 변환합니다."""
    nodes = []
    edges = []

    def traverse(node, parent_id=None):
        node_id = node["topic"]
        # 노드가 이미 추가되었는지 확인 (동일한 주제가 다른 가지에 있을 수 있음)
        if node_id not in [n.id for n in nodes]:
            nodes.append(Node(id=node_id, label=node_id, size=25))

        if parent_id:
            edges.append(Edge(source=parent_id, target=node_id, type="CURVE_SMOOTH"))

        if node.get("children"):
            for child in node["children"]:
                traverse(child, parent_id=node_id)

    traverse(mindmap_data["mindmap"])
    return nodes, edges


# --- Streamlit App ---

st.set_page_config(page_title="AutoBrief AI", layout="wide")
st.title("AutoBrief AI 🚀")
st.write(
    "문서 그룹을 만들고, 문서를 업로드하여 AI와 대화하고 지식 마인드맵을 생성하세요."
)

# --- Sidebar ---
with st.sidebar:
    st.header("Project Management")
    groups = get_project_groups()
    selected_group = st.selectbox(
        "프로젝트 그룹 선택", options=groups, index=0 if groups else None
    )

    st.divider()
    st.subheader("새 그룹 생성")
    with st.form("new_group_form", clear_on_submit=True):
        new_group_name = st.text_input("새 그룹 이름")
        if st.form_submit_button("생성"):
            if new_group_name:
                result = add_project_group(new_group_name)
                if result:
                    st.success(f"그룹 '{new_group_name}' 생성 완료!")
                    st.rerun()  # 그룹 목록을 새로고침하기 위해 재실행
            else:
                st.warning("그룹 이름을 입력하세요.")

    if selected_group:
        st.divider()
        st.subheader(f"'{selected_group}' 관리")

        # --- 수정된 파일 업로드 로직 ---
        uploaded_file = st.file_uploader("문서 선택", type=None)
        if st.button("선택한 파일 업로드", disabled=not uploaded_file):
            with st.spinner(f"'{uploaded_file.name}' 업로드 및 처리 중..."):
                result = upload_document(selected_group, uploaded_file)
                if result:
                    st.success("파일 처리 요청 완료! 잠시 후 반영됩니다.")
        # --- 여기까지 수정 ---

        if st.button("현재 그룹 삭제", type="primary"):
            if delete_project_group(selected_group):
                st.success(f"그룹 '{selected_group}' 삭제 완료!")
                st.rerun()

# --- Main Content ---
if selected_group:
    group_name = selected_group
    chat_tab, summary_tab, mindmap_tab = st.tabs(
        ["🤖 AI Chat", "📄 문서 요약", "🗺️ 마인드맵"]
    )

    with chat_tab:
        st.header(f"`{group_name}` 그룹과 대화하기")
        if (
            "messages" not in st.session_state
            or st.session_state.get("current_group") != group_name
        ):
            st.session_state.messages = []
            st.session_state.current_group = group_name

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("문서에 대해 질문하세요"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("답변을 생각하는 중..."):
                    response = post_chat(group_name, prompt)
                    if response:
                        answer = response.get(
                            "answer", "죄송합니다, 답변을 생성할 수 없습니다."
                        )
                        sources = response.get("sources", [])
                        full_response = answer
                        if sources:
                            full_response += "\n\n--- \n**참고 자료:**\n"
                            for i, source in enumerate(sources):
                                content = source.get("content", "")
                                full_response += f"- {content[:100]}...\n"
                        st.markdown(full_response)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": full_response}
                        )

    with summary_tab:
        st.header(f"`{group_name}` 그룹의 문서 요약")
        if st.button("요약 불러오기"):
            summaries = get_summaries(group_name)
            if summaries:
                for summary in summaries:
                    with st.expander(f"**📄 {summary['file_name']}**"):
                        st.write(summary["summary"])
            else:
                st.info(
                    "표시할 요약이 없습니다. 문서를 업로드하고 처리가 완료될 때까지 기다려주세요."
                )

    with mindmap_tab:
        st.header(f"`{group_name}` 그룹의 마인드맵")
        if st.button("마인드맵 생성/새로고침"):
            with st.spinner("마인드맵 데이터를 불러오는 중..."):
                mindmap_data = get_mindmap(group_name)
                if mindmap_data:
                    nodes, edges = build_mindmap_graph(mindmap_data)
                    config = Config(
                        width=1200,
                        height=800,
                        directed=True,
                        physics=True,
                        hierarchical=False,
                    )
                    agraph(nodes=nodes, edges=edges, config=config)
                else:
                    st.warning(
                        "표시할 마인드맵이 없습니다. 문서를 업로드하고 처리가 완료될 때까지 기다려주세요."
                    )
else:
    st.info("👈 사이드바에서 프로젝트 그룹을 선택하거나 새로 생성해주세요.")

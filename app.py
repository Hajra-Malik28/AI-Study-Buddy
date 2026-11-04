import html
import re
from pathlib import Path

import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash

import database as db
from ai_utils import (
    SUMMARY_MODES,
    AIError,
    ai_available,
    chat_reply,
    extract_text,
    generate_quiz,
    summarize,
)

# ------------------------------------------------------------------ setup

st.set_page_config(
    page_title="AI Study Buddy",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

db.init_db()

CSS_PATH = Path(__file__).parent / "static" / "style.css"
if CSS_PATH.exists():
    st.markdown(
        f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>",
        unsafe_allow_html=True,
    )

MAX_UPLOAD_MB = 10
ALLOWED_TYPES = ["pdf", "docx", "pptx", "txt", "md"]

defaults = {
    "page": "Home",
    "user_id": None,
    "user_name": None,
    "uploader_key": 0,
    "active_chat_id": 0,
    "pending_chat_id": None,
    "quiz": None,
    "summary": None,
    "flash": None,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------------- helpers

def html_block(markup: str):
    """Render HTML safely in Streamlit.

    Markdown treats indented lines / blank lines as code blocks, so we strip
    indentation and blank lines before rendering.
    """
    cleaned = "\n".join(line.strip() for line in markup.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


def go_to(page: str):
    st.session_state.page = page
    st.rerun()


def page_header(label: str, title: str, subtitle: str):
    html_block(
        f"""
        <div class="page-header">
            <span class="eyebrow">{html.escape(label)}</span>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
        </div>
        """
    )


def show_flash():
    if st.session_state.flash:
        st.success(st.session_state.flash)
        st.session_state.flash = None


def empty_state(icon: str, title: str, text: str):
    html_block(
        f"""
        <div class="empty-state">
            <div class="empty-icon">{icon}</div>
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(text)}</p>
        </div>
        """
    )


def need_ai_key() -> bool:
    if ai_available():
        return False
    st.warning(
        "AI is not connected yet. Add your `GROQ_API_KEY` in the app secrets "
        "(see README) to use this feature."
    )
    return True


# --------------------------------------------------------------- database

def get_user_stats(user_id):
    with db.get_connection() as conn:
        documents = conn.execute(
            "SELECT COUNT(*) AS total FROM documents WHERE user_id = ?", (user_id,)
        ).fetchone()["total"]
        chats = conn.execute(
            "SELECT COUNT(*) AS total FROM chats WHERE user_id = ?", (user_id,)
        ).fetchone()["total"]
        quizzes = conn.execute(
            "SELECT COUNT(*) AS total FROM quiz_sessions WHERE user_id = ?", (user_id,)
        ).fetchone()["total"]
    return documents, chats, quizzes


def create_account(name, email, password):
    with db.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        return cur.lastrowid


def authenticate_user(email, password):
    with db.get_connection() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def logout():
    for key, value in defaults.items():
        st.session_state[key] = value
    st.rerun()


# ---------------------------------------------------------------- sidebar

def sidebar():
    with st.sidebar:
        html_block(
            """
            <div class="side-brand">
                <span class="side-brand-icon">S</span>
                <div>
                    <strong>Study Buddy</strong>
                    <small>Your AI learning space</small>
                </div>
            </div>
            """
        )
        st.divider()

        if st.session_state.user_id:
            st.markdown(
                f"<p class='side-user'>Signed in as<br>"
                f"<strong>{html.escape(st.session_state.user_name or '')}</strong></p>",
                unsafe_allow_html=True,
            )
            nav = [
                ("Dashboard", "🏠  Dashboard"),
                ("Documents", "📁  My Documents"),
                ("Chat", "💬  AI Study Chat"),
                ("Quiz", "📝  Quiz Preparation"),
            ]
            for page, label in nav:
                active = st.session_state.page == page
                if st.button(
                    label,
                    key=f"nav_{page}",
                    use_container_width=True,
                    type="primary" if active else "secondary",
                ):
                    go_to(page)
            st.divider()
            if st.button("↪  Log out", key="nav_logout", use_container_width=True):
                logout()
        else:
            for page, label in [("Home", "Home"), ("Login", "Log in"), ("Signup", "Sign up")]:
                active = st.session_state.page == page
                if st.button(
                    label,
                    key=f"nav_{page}",
                    use_container_width=True,
                    type="primary" if active else "secondary",
                ):
                    go_to(page)


sidebar()


# --------------------------------------------------------------- home page

def home_page():
    html_block(
        """
        <div class="landing-hero">
            <div class="landing-left">
                <div class="landing-badge">✦ YOUR PERSONAL AI LEARNING PLATFORM</div>
                <h1>Learn smarter.<br><span>Grow faster.</span></h1>
                <p class="landing-description">
                    Upload your notes, ask questions, understand difficult
                    topics and prepare for your exams with confidence.
                </p>
                <div class="landing-points">
                    <div>✓ Learn from your own study material</div>
                    <div>✓ Get instant, easy explanations</div>
                    <div>✓ Practice with quizzes made from your notes</div>
                </div>
            </div>
            <div class="landing-right">
                <div class="workspace-preview">
                    <div class="preview-top">
                        <div>
                            <span class="preview-label">YOUR WORKSPACE</span>
                            <h3>Study Overview</h3>
                        </div>
                        <span class="preview-status">● ACTIVE</span>
                    </div>
                    <div class="preview-highlight">
                        <span>✦</span>
                        <div>
                            <strong>Your AI Study Assistant</strong>
                            <p>Everything you need to learn in one place.</p>
                        </div>
                    </div>
                    <div class="preview-item">
                        <div class="preview-icon">💬</div>
                        <div><strong>AI Study Chat</strong><p>Understand difficult concepts</p></div>
                        <span class="preview-arrow">↗</span>
                    </div>
                    <div class="preview-item">
                        <div class="preview-icon">📁</div>
                        <div><strong>Smart Documents</strong><p>Organize your learning material</p></div>
                        <span class="preview-arrow">↗</span>
                    </div>
                    <div class="preview-item">
                        <div class="preview-icon">📝</div>
                        <div><strong>Exam Preparation</strong><p>Practice and test your knowledge</p></div>
                        <span class="preview-arrow">↗</span>
                    </div>
                    <div class="preview-footer">YOUR LEARNING JOURNEY STARTS HERE</div>
                </div>
            </div>
        </div>
        """
    )

    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("Get started free", type="primary", use_container_width=True):
            go_to("Signup")
    with col2:
        if st.button("Log in", use_container_width=True, key="home_login"):
            go_to("Login")

    html_block(
        """
        <div class="landing-section-heading">
            <span class="landing-section-label">WHAT YOU CAN DO</span>
            <h2>Everything you need to study better</h2>
            <p>One platform for notes, questions and exam practice.</p>
        </div>
        <div class="landing-feature-grid">
            <div class="landing-feature">
                <div class="landing-feature-icon">💬</div>
                <h3>AI Study Chat</h3>
                <p>Ask questions about your uploaded notes and get simple explanations with examples.</p>
            </div>
            <div class="landing-feature">
                <div class="landing-feature-icon">📁</div>
                <h3>Smart Library</h3>
                <p>Upload PDF, Word, PowerPoint and text files and keep them organised in one place.</p>
            </div>
            <div class="landing-feature">
                <div class="landing-feature-icon">📝</div>
                <h3>Exam Preparation</h3>
                <p>Generate MCQ quizzes, summaries and likely exam questions from your own material.</p>
            </div>
        </div>
        <div class="landing-section-heading">
            <span class="landing-section-label">HOW IT WORKS</span>
            <h2>Three steps to start</h2>
        </div>
        <div class="landing-feature-grid">
            <div class="landing-feature">
                <span class="landing-feature-number">01</span>
                <h3>Upload your notes</h3>
                <p>Add lecture slides, handouts or notes to your library.</p>
            </div>
            <div class="landing-feature">
                <span class="landing-feature-number">02</span>
                <h3>Ask or summarise</h3>
                <p>Chat with your material or get a quick summary of a long chapter.</p>
            </div>
            <div class="landing-feature">
                <span class="landing-feature-number">03</span>
                <h3>Practice and improve</h3>
                <p>Take a quiz, see your score and read the explanation for every answer.</p>
            </div>
        </div>
        <div class="site-footer">AI Study Buddy · Built with Python and Streamlit</div>
        """
    )


# -------------------------------------------------------------- auth pages

def auth_intro(eyebrow: str, title: str, text: str):
    html_block(
        f"""
        <div class="auth-intro">
            <span class="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{text}</p>
            <div class="auth-benefit">✦ Learn difficult topics easily</div>
            <div class="auth-benefit">✦ Study with your own notes</div>
            <div class="auth-benefit">✦ Practice for your exams</div>
        </div>
        """
    )


def signup_page():
    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        auth_intro(
            "START YOUR JOURNEY",
            "Your next learning chapter starts here.",
            "Create your personal study space and keep your learning organised.",
        )

    with right:
        html_block(
            """
            <div class="auth-heading">Create your account</div>
            <div class="auth-subtitle">Enter your details to get started.</div>
            """
        )
        with st.form("signup_form"):
            name = st.text_input("Full name", placeholder="Your full name", max_chars=100)
            email = st.text_input("Email address", placeholder="you@example.com", max_chars=254)
            password = st.text_input("Password", type="password", placeholder="At least 8 characters")
            confirm = st.text_input("Confirm password", type="password", placeholder="Enter password again")
            submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)

        if submitted:
            name = name.strip()
            email = email.strip().lower()

            if not (name and email and password and confirm):
                st.error("Please fill in all fields.")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                st.error("Please enter a valid email address.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            elif password != confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    user_id = create_account(name, email, password)
                except Exception as error:
                    if "UNIQUE constraint failed" in str(error):
                        st.error("This email is already registered. Try logging in.")
                    else:
                        st.error("Could not create the account. Please try again.")
                else:
                    st.session_state.user_id = user_id
                    st.session_state.user_name = name
                    st.session_state.page = "Dashboard"
                    st.rerun()

        st.markdown('<p class="muted-text">Already have an account?</p>', unsafe_allow_html=True)
        if st.button("Log in instead", use_container_width=True, key="to_login"):
            go_to("Login")


def login_page():
    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        auth_intro(
            "WELCOME BACK",
            "Pick up where your learning left off.",
            "Your personal AI learning space for notes, questions and exam preparation.",
        )

    with right:
        html_block(
            """
            <div class="auth-heading">Welcome back!</div>
            <div class="auth-subtitle">Log in to continue your learning.</div>
            """
        )
        with st.form("login_form"):
            email = st.text_input("Email address", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)

        if submitted:
            user = authenticate_user(email.strip().lower(), password)
            if user:
                st.session_state.user_id = user["id"]
                st.session_state.user_name = user["name"]
                st.session_state.page = "Dashboard"
                st.rerun()
            else:
                st.error("Incorrect email or password.")

        st.markdown('<p class="muted-text">New to Study Buddy?</p>', unsafe_allow_html=True)
        if st.button("Create an account", use_container_width=True, key="to_signup"):
            go_to("Signup")


# -------------------------------------------------------------- dashboard

def dashboard_page():
    uid = st.session_state.user_id
    documents, chats, quizzes = get_user_stats(uid)
    safe_name = html.escape(st.session_state.user_name or "Student")

    html_block(
        f"""
        <div class="hero-card">
            <span class="hero-tag">YOUR PERSONAL LEARNING SPACE</span>
            <h1>Welcome, {safe_name}!</h1>
            <p>What would you like to study today?</p>
        </div>
        """
    )

    st.markdown("### Your learning activity")
    cols = st.columns(3)
    stats = [("📁 My documents", documents), ("💬 Study chats", chats), ("📝 Practice sessions", quizzes)]
    for col, (label, value) in zip(cols, stats):
        with col:
            html_block(
                f"""
                <div class="stat-card">
                    <p>{label}</p>
                    <h2>{value}</h2>
                </div>
                """
            )

    st.write("")
    st.markdown("### My learning tools")
    tools = [
        ("💬", "AI Study Chat", "Ask questions about your notes and understand topics.", "Open chat →", "Chat"),
        ("📁", "My Documents", "Upload and manage your study material.", "View documents →", "Documents"),
        ("📝", "Quiz Preparation", "Generate MCQs and summaries to prepare for exams.", "Start preparing →", "Quiz"),
    ]
    cols = st.columns(3)
    for col, (icon, title, text, button, page) in zip(cols, tools):
        with col:
            html_block(
                f"""
                <div class="tool-card">
                    <span class="tool-number">{icon}</span>
                    <h3>{title}</h3>
                    <p>{text}</p>
                </div>
                """
            )
            if st.button(button, use_container_width=True, key=f"tool_{page}"):
                go_to(page)

    docs = db.list_documents(uid)[:3]
    if docs:
        st.write("")
        st.markdown("### Recently added")
        for d in docs:
            html_block(
                f"""
                <div class="recent-row">
                    <span>📄 {html.escape(d['filename'])}</span>
                    <small>{d['uploaded_at'][:10]}</small>
                </div>
                """
            )


# -------------------------------------------------------------- documents

def documents_page():
    uid = st.session_state.user_id
    page_header("LEARNING TOOL", "My Documents", "Upload, view and manage all your study material in one place.")
    show_flash()

    with st.container(border=True):
        st.markdown("#### Upload new material")
        files = st.file_uploader(
            f"PDF, Word, PowerPoint or text files (max {MAX_UPLOAD_MB} MB each)",
            type=ALLOWED_TYPES,
            accept_multiple_files=True,
            key=f"uploader_{st.session_state.uploader_key}",
        )
        if st.button("Save to library", type="primary", disabled=not files):
            saved = 0
            for f in files:
                if f.size > MAX_UPLOAD_MB * 1024 * 1024:
                    st.error(f"{f.name}: file is larger than {MAX_UPLOAD_MB} MB.")
                    continue
                try:
                    text = extract_text(f)
                except Exception:
                    st.error(f"{f.name}: could not read this file.")
                    continue
                if len(text.strip()) < 20:
                    st.warning(f"{f.name}: no readable text found (scanned PDFs are not supported).")
                    continue
                db.add_document(uid, f.name, text)
                saved += 1
            if saved:
                st.session_state.uploader_key += 1
                st.session_state.flash = f"{saved} document(s) saved to your library."
                st.rerun()

    st.write("")
    docs = db.list_documents(uid)
    st.markdown(f"#### Your library ({len(docs)})")

    if not docs:
        empty_state("📂", "Your library is empty", "Upload your first notes above to start chatting and practising.")
        return

    for d in docs:
        with st.container(border=True):
            info, action = st.columns([5, 1])
            with info:
                st.markdown(f"**📄 {d['filename']}**")
                st.caption(f"Added {d['uploaded_at'][:10]} · {d['chars']:,} characters")
            with action:
                if st.button("Delete", key=f"del_{d['id']}", use_container_width=True):
                    db.delete_document(uid, d["id"])
                    st.session_state.flash = f"“{d['filename']}” was deleted."
                    st.rerun()
            with st.expander("Preview"):
                preview = d["content"][:1500]
                st.text(preview + ("…" if len(d["content"]) > 1500 else ""))


# ------------------------------------------------------------------- chat

def chat_page():
    uid = st.session_state.user_id
    page_header("LEARNING TOOL", "AI Study Chat", "Ask questions and understand your study material.")

    if need_ai_key():
        return

    # apply a chat selection requested during the previous run
    if st.session_state.pending_chat_id is not None:
        st.session_state.active_chat_id = st.session_state.pending_chat_id
        st.session_state.pending_chat_id = None

    docs = db.list_documents(uid)
    chats = db.list_chats(uid)
    doc_names = {d["id"]: d["filename"] for d in docs}
    chat_titles = {c["id"]: c["title"] for c in chats}

    if st.session_state.active_chat_id not in chat_titles:
        st.session_state.active_chat_id = 0

    top_left, top_mid, top_right = st.columns([3, 3, 1])
    with top_left:
        st.selectbox(
            "Conversation",
            options=[0] + list(chat_titles),
            format_func=lambda i: "➕ New chat" if i == 0 else chat_titles[i],
            key="active_chat_id",
        )
    active = st.session_state.active_chat_id
    chat_row = db.get_chat(uid, active) if active else None

    selected_doc = None
    with top_mid:
        if active == 0:
            selected_doc = st.selectbox(
                "Study material",
                options=[None] + list(doc_names),
                format_func=lambda i: "General question (no document)" if i is None else doc_names[i],
                key="new_chat_doc",
            )
        else:
            doc_id = chat_row["document_id"] if chat_row else None
            st.text_input(
                "Study material",
                value=doc_names.get(doc_id, "General question (no document)"),
                disabled=True,
            )
    with top_right:
        if active:
            st.write("")
            st.write("")
            if st.button("Delete", key="del_chat", use_container_width=True):
                db.delete_chat(uid, active)
                st.session_state.pending_chat_id = 0
                st.rerun()

    if active == 0 and not docs:
        st.info("Tip: upload a document first so the AI can answer from your notes.")

    history = [dict(m) for m in db.get_messages(active)] if active else []

    if not history:
        empty_state("💬", "Start a conversation", "Ask about a topic, a definition, or a hard concept from your notes.")

    for m in history:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("Ask a question about your study material…")
    if not prompt:
        return

    with st.chat_message("user"):
        st.markdown(prompt)

    if active == 0:
        title = prompt.strip().replace("\n", " ")[:45]
        active = db.create_chat(uid, selected_doc, title)
        doc_id = selected_doc
    else:
        doc_id = chat_row["document_id"]

    db.add_message(active, "user", prompt)
    history.append({"role": "user", "content": prompt})

    doc_text = None
    if doc_id:
        doc = db.get_document(uid, doc_id)
        doc_text = doc["content"] if doc else None

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                answer = chat_reply(history, doc_text)
            except AIError as error:
                st.error(str(error))
                st.session_state.pending_chat_id = active
                return
        st.markdown(answer)

    db.add_message(active, "assistant", answer)
    st.session_state.pending_chat_id = active
    st.rerun()


# ------------------------------------------------------------------- quiz

def render_quiz(quiz: dict):
    uid = st.session_state.user_id
    questions = quiz["questions"]

    if not quiz["submitted"]:
        st.markdown(f"**{quiz['doc_name']}** · {quiz['difficulty']} · {len(questions)} questions")
        with st.form("quiz_form"):
            for i, q in enumerate(questions):
                st.markdown(f"**Q{i + 1}. {q['question']}**")
                st.radio(
                    "Choose one",
                    options=[0, 1, 2, 3],
                    format_func=lambda idx, opts=q["options"]: f"{'ABCD'[idx]}.  {opts[idx]}",
                    index=None,
                    key=f"q_{i}",
                    label_visibility="collapsed",
                )
                st.write("")
            submitted = st.form_submit_button("Submit answers", type="primary", use_container_width=True)

        if submitted:
            answers = [st.session_state.get(f"q_{i}") for i in range(len(questions))]
            score = sum(1 for a, q in zip(answers, questions) if a == q["answer_index"])
            quiz.update(submitted=True, answers=answers, score=score)
            db.add_quiz_session(
                uid, quiz["doc_id"], quiz["doc_name"], quiz["difficulty"], score, len(questions)
            )
            st.rerun()
        if st.button("Cancel quiz", key="cancel_quiz"):
            st.session_state.quiz = None
            st.rerun()
        return

    # ---- results
    total = len(questions)
    score = quiz["score"]
    percent = round(score / total * 100)
    verdict = "Excellent work!" if percent >= 80 else "Good effort, keep practising." if percent >= 50 else "Review the topic and try again."
    html_block(
        f"""
        <div class="score-card">
            <span>Your score</span>
            <h2>{score} / {total}</h2>
            <p>{percent}% · {verdict}</p>
        </div>
        """
    )

    for i, (q, chosen) in enumerate(zip(questions, quiz["answers"])):
        correct = chosen == q["answer_index"]
        status = "result-correct" if correct else "result-wrong"
        chosen_text = "Not answered" if chosen is None else f"{'ABCD'[chosen]}. {q['options'][chosen]}"
        right_text = f"{'ABCD'[q['answer_index']]}. {q['options'][q['answer_index']]}"
        html_block(
            f"""
            <div class="result-card {status}">
                <strong>Q{i + 1}. {html.escape(q['question'])}</strong>
                <p>Your answer: {html.escape(chosen_text)}</p>
                {'' if correct else f'<p>Correct answer: {html.escape(right_text)}</p>'}
                <small>{html.escape(q['explanation'])}</small>
            </div>
            """
        )

    if st.button("Start a new quiz", type="primary", key="new_quiz"):
        for i in range(len(questions)):
            st.session_state.pop(f"q_{i}", None)
        st.session_state.quiz = None
        st.rerun()


def quiz_page():
    uid = st.session_state.user_id
    page_header("LEARNING TOOL", "Quiz Preparation", "Practise with quizzes and summaries made from your own notes.")

    docs = db.list_documents(uid)
    if not docs:
        empty_state("📝", "No documents yet", "Upload study material first, then come back to generate quizzes.")
        if st.button("Go to My Documents", type="primary"):
            go_to("Documents")
        return

    doc_map = {d["id"]: d for d in docs}
    tab_quiz, tab_summary, tab_history = st.tabs(["MCQ quiz", "Summaries", "Past results"])

    with tab_quiz:
        quiz = st.session_state.quiz
        if quiz:
            render_quiz(quiz)
        elif not need_ai_key():
            c1, c2, c3 = st.columns([3, 1, 1])
            doc_id = c1.selectbox("Document", list(doc_map), format_func=lambda i: doc_map[i]["filename"], key="quiz_doc")
            count = c2.selectbox("Questions", [5, 10, 15], key="quiz_count")
            difficulty = c3.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1, key="quiz_diff")
            if st.button("Generate quiz", type="primary"):
                with st.spinner("Creating your questions…"):
                    try:
                        questions = generate_quiz(doc_map[doc_id]["content"], count, difficulty)
                    except AIError as error:
                        st.error(str(error))
                    else:
                        st.session_state.quiz = {
                            "doc_id": doc_id,
                            "doc_name": doc_map[doc_id]["filename"],
                            "difficulty": difficulty,
                            "questions": questions,
                            "submitted": False,
                        }
                        st.rerun()

    with tab_summary:
        if not need_ai_key():
            c1, c2 = st.columns([3, 2])
            sdoc = c1.selectbox("Document", list(doc_map), format_func=lambda i: doc_map[i]["filename"], key="sum_doc")
            mode = c2.selectbox("What do you need?", list(SUMMARY_MODES), key="sum_mode")
            if st.button("Generate", type="primary", key="sum_btn"):
                with st.spinner("Reading your notes…"):
                    try:
                        st.session_state.summary = summarize(doc_map[sdoc]["content"], mode)
                    except AIError as error:
                        st.session_state.summary = None
                        st.error(str(error))
            if st.session_state.summary:
                with st.container(border=True):
                    st.markdown(st.session_state.summary)

    with tab_history:
        sessions = db.list_quiz_sessions(uid)
        if not sessions:
            empty_state("📊", "No results yet", "Finish a quiz and your scores will appear here.")
        else:
            rows = [
                {
                    "Date": s["created_at"][:16],
                    "Document": s["document_name"],
                    "Difficulty": s["difficulty"],
                    "Score": f"{s['score']} / {s['total']}",
                }
                for s in sessions
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------- routing

if st.session_state.user_id is None:
    if st.session_state.page == "Signup":
        signup_page()
    elif st.session_state.page == "Login":
        login_page()
    else:
        home_page()
else:
    page = st.session_state.page
    if page == "Documents":
        documents_page()
    elif page == "Chat":
        chat_page()
    elif page == "Quiz":
        quiz_page()
    else:
        st.session_state.page = "Dashboard"
        dashboard_page()
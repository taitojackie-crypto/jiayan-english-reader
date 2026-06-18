import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from modules.material_loader import MaterialLoader
from modules.reading_session import ProjectStore, ReadingTutor
from modules.spelling import SpellingExercise
from modules.tts_engine import TTSEngine
from modules.vocabulary import VocabularyBuilder

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "jiayan-english-dev")

BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / os.environ.get("UPLOAD_FOLDER", "data/uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

ARTICLE_DIR = BASE_DIR / "data" / "articles"
ARTICLE_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = BASE_DIR / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_DIR = BASE_DIR / "data" / "sessions"
PROJECT_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "10"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "bmp",
    "webp",
    "pdf",
    "docx",
    "txt",
    "md",
}

loader = MaterialLoader()
project_store = ProjectStore(str(PROJECT_DIR))
tutor = ReadingTutor(project_store=project_store)
tts_engine = TTSEngine(output_dir=str(AUDIO_DIR))
vocab_builder = VocabularyBuilder()


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_article(text: str, title: str = "") -> str:
    article_id = str(uuid4())
    filepath = ARTICLE_DIR / f"{article_id}.json"
    data = {
        "id": article_id,
        "title": title,
        "text": text,
        "created_at": datetime.now().isoformat(),
    }
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return article_id


def _load_article(article_id: str) -> dict:
    filepath = ARTICLE_DIR / f"{article_id}.json"
    return json.loads(filepath.read_text(encoding="utf-8"))


@app.route("/")
def index():
    projects = project_store.list_all()
    return render_template("index.html", projects=projects)


@app.route("/load_material", methods=["POST"])
def load_material():
    source_type = request.form.get("source_type", "text")
    text = ""
    title = ""

    try:
        if source_type == "file":
            file = request.files.get("file")
            if not file or not file.filename:
                return jsonify({"error": "请选择文件"}), 400
            if not _allowed_file(file.filename):
                return jsonify({"error": "不支持的文件格式"}), 400

            filename = secure_filename(file.filename)
            filepath = UPLOAD_FOLDER / filename
            file.save(filepath)
            text = loader.load(filepath)
            title = Path(filename).stem

        elif source_type == "url":
            url = request.form.get("url", "").strip()
            if not url:
                return jsonify({"error": "请输入链接"}), 400
            text = loader.load(url, source_type="url")
            title = "来自网络"

        elif source_type == "text":
            text = request.form.get("text", "").strip()
            if not text:
                return jsonify({"error": "请输入文本"}), 400
            title = "粘贴文本"

        else:
            return jsonify({"error": "未知来源类型"}), 400

        article_id = _save_article(text, title=title)
        session = tutor.create_session(text, article_id=article_id)
        return redirect(url_for("read", article_id=article_id, session_id=session.session_id))

    except Exception as exc:
        return jsonify({"error": f"加载失败：{exc}"}), 500


@app.route("/read/<article_id>")
def read(article_id: str):
    session_id = request.args.get("session_id", "")
    try:
        article = _load_article(article_id)
    except Exception:
        return "Article not found", 404

    session = None
    if session_id:
        session = tutor.restore_session(session_id)

    if not session:
        session = tutor.create_session(article["text"], article_id=article_id)
        session_id = session.session_id

    reading_text = session.get_reading_text()

    return render_template(
        "reading.html",
        article=article,
        reading_text=reading_text,
        session_id=session_id,
    )


@app.route("/api/projects")
def api_projects():
    return jsonify({"projects": project_store.list_all()})


@app.route("/api/projects/delete", methods=["POST"])
def api_projects_delete():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "").strip()
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    if session_id in tutor.sessions:
        del tutor.sessions[session_id]
    project_store.delete(session_id)
    return jsonify({"success": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "")
    question = data.get("question", "").strip()

    if not session_id or not question:
        return jsonify({"error": "缺少参数"}), 400

    try:
        answer = tutor.ask(session_id, question)
        return jsonify({"answer": answer})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500




@app.route("/api/translate", methods=["POST"])
def api_translate():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "")
    text = data.get("text", "").strip()
    if not session_id or not text:
        return jsonify({"error": "缺少参数"}), 400

    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "未找到阅读会话"}), 404

    try:
        translation = tutor.translate(text, context=session.article)
        return jsonify({"translation": translation})
    except Exception as exc:
        return jsonify({"error": f"翻译失败：{exc}"}), 500


@app.route("/api/explain", methods=["POST"])
def api_explain():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "")
    text = data.get("text", "").strip()
    if not session_id or not text:
        return jsonify({"error": "缺少参数"}), 400

    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "未找到阅读会话"}), 404

    try:
        explanation = tutor.explain(text, context=session.article)
        return jsonify({"explanation": explanation})
    except Exception as exc:
        return jsonify({"error": f"解释失败：{exc}"}), 500

@app.route("/api/tts", methods=["POST"])
def api_tts():
    data = request.get_json(force=True) or {}
    text = data.get("text", "").strip()
    session_id = data.get("session_id", "")
    if not text:
        return jsonify({"error": "文本为空"}), 400

    voice = None
    speed = None
    if session_id:
        session = tutor.get_session(session_id)
        if session:
            if session.get_voice():
                voice = session.get_voice()
            speed = session.get_speed()

    try:
        audio_path = tts_engine.speak(text, voice=voice, speed=speed)
        filename = Path(audio_path).name
        return jsonify({"audio_url": url_for("serve_audio", filename=filename)})
    except Exception as exc:
        return jsonify({"error": f"语音生成失败：{exc}"}), 500


@app.route("/api/tts/precache", methods=["POST"])
def api_tts_precache():
    data = request.get_json(force=True) or {}
    text = data.get("text", "").strip()
    session_id = data.get("session_id", "")
    if not text:
        return jsonify({"error": "文本为空"}), 400

    voice = None
    speed = None
    if session_id:
        session = tutor.get_session(session_id)
        if session:
            if session.get_voice():
                voice = session.get_voice()
            speed = session.get_speed()

    try:
        audio_path = tts_engine.speak(text, voice=voice, speed=speed)
        filename = Path(audio_path).name
        return jsonify({"audio_url": url_for("serve_audio", filename=filename)})
    except Exception as exc:
        return jsonify({"error": f"语音生成失败：{exc}"}), 500


@app.route("/api/voices")
def api_voices():
    return jsonify({"voices": tts_engine.list_voices(), "default": tts_engine.DEFAULT_VOICE})


@app.route("/api/voice", methods=["GET", "POST"])
def api_voice():
    if request.method == "GET":
        session_id = request.args.get("session_id", "")
    else:
        data = request.get_json(force=True) or {}
        session_id = request.args.get("session_id") or request.form.get("session_id") or data.get("session_id", "")
    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    if request.method == "GET":
        return jsonify({"voice": session.get_voice() or tts_engine.DEFAULT_VOICE})

    data = request.get_json(force=True) or {}
    voice = data.get("voice", "").strip()
    if not voice:
        return jsonify({"error": "Missing voice"}), 400

    session.set_voice(voice)
    return jsonify({"success": True, "voice": voice})


@app.route("/api/speed", methods=["GET", "POST"])
def api_speed():
    if request.method == "GET":
        session_id = request.args.get("session_id", "")
    else:
        data = request.get_json(force=True) or {}
        session_id = request.args.get("session_id") or request.form.get("session_id") or data.get("session_id", "")
    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    if request.method == "GET":
        return jsonify({"speed": session.get_speed()})

    data = request.get_json(force=True) or {}
    try:
        speed = float(data.get("speed", 1.0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid speed"}), 400

    session.set_speed(speed)
    return jsonify({"success": True, "speed": session.get_speed()})


@app.route("/audio/<filename>")
def serve_audio(filename: str):
    return send_from_directory(AUDIO_DIR, filename)


@app.route("/api/vocab")
def api_vocab():
    session_id = request.args.get("session_id", "")
    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    words = session.get_vocab(vocab_builder)
    return jsonify({"words": words})


@app.route("/api/vocab/add", methods=["POST"])
def api_vocab_add():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "")
    word = data.get("word", "").strip()
    if not session_id or not word:
        return jsonify({"error": "Missing parameters"}), 400

    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    session.add_custom_word(word)
    return jsonify({"success": True, "words": session.get_vocab(vocab_builder)})


@app.route("/api/vocab/delete", methods=["POST"])
def api_vocab_delete():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "")
    word = data.get("word", "").strip()
    if not session_id or not word:
        return jsonify({"error": "Missing parameters"}), 400

    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    session.remove_word(word)
    return jsonify({"success": True, "words": session.get_vocab(vocab_builder)})


@app.route("/api/vocab/export")
def api_vocab_export():
    session_id = request.args.get("session_id", "")
    session = tutor.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    csv = session.export_vocab_csv(vocab_builder)
    return Response(
        csv,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=vocabulary.csv"},
    )


@app.route("/api/spelling", methods=["GET", "POST"])
def api_spelling():
    if request.method == "GET":
        session_id = request.args.get("session_id", "")
        session = tutor.get_session(session_id)
        if not session:
            return jsonify({"error": "未找到阅读会话"}), 404
        exercise = SpellingExercise(session.article)
        return jsonify({"words": exercise.get_words()})

    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "")
    target = data.get("target", "").strip()
    attempt = data.get("attempt", "").strip()

    session = tutor.get_session(session_id)
    if not session or not target:
        return jsonify({"error": "缺少参数"}), 400

    exercise = SpellingExercise(session.article)
    result = exercise.check(target, attempt)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

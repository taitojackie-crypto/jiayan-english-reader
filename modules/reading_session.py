import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Union
from uuid import uuid4

from modules.vocabulary import VocabularyBuilder


@dataclass
class ReadingSession:
    session_id: str
    article: str
    grade: int = 2
    messages: List[dict] = field(default_factory=list)
    formatted_text: str = ""
    custom_vocab: List[str] = field(default_factory=list)
    removed_words: Set[str] = field(default_factory=set)
    voice: str = ""
    speed: float = 1.0
    article_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def get_reading_text(self) -> str:
        return self.formatted_text if self.formatted_text else self.article

    def add_custom_word(self, word: str) -> None:
        word = word.strip().lower()
        if word and word not in self.custom_vocab:
            self.custom_vocab.append(word)
        self.removed_words.discard(word)
        self.touch()

    def remove_word(self, word: str) -> None:
        word = word.strip().lower()
        self.removed_words.add(word)
        if word in self.custom_vocab:
            self.custom_vocab.remove(word)
        self.touch()

    def set_voice(self, voice: str) -> None:
        self.voice = voice.strip()
        self.touch()

    def set_speed(self, speed: float) -> None:
        try:
            self.speed = float(speed)
        except (ValueError, TypeError):
            self.speed = 1.0
        self.touch()

    def get_voice(self) -> str:
        return self.voice

    def get_speed(self) -> float:
        return self.speed

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.touch()

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()

    def get_vocab(self, vocab_builder) -> List[Dict[str, object]]:
        extracted = vocab_builder.extract(self.article, top_n=50)
        filtered = [item for item in extracted if item["word"] not in self.removed_words]
        existing = {item["word"] for item in filtered}
        for word in self.custom_vocab:
            if word not in existing:
                filtered.append({
                    "word": word,
                    "count": 1,
                    "level": vocab_builder._guess_level(word),
                })
                existing.add(word)
        return filtered[:20]

    def export_vocab_csv(self, vocab_builder) -> str:
        lines = ["word,count,level"]
        for item in self.get_vocab(vocab_builder):
            lines.append(f"{item['word']},{item['count']},{item['level']}")
        return "\n".join(lines)

    def get_voice(self) -> str:
        return self.voice

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "article_id": self.article_id,
            "article": self.article,
            "grade": self.grade,
            "messages": self.messages,
            "formatted_text": self.formatted_text,
            "custom_vocab": self.custom_vocab,
            "removed_words": list(self.removed_words),
            "voice": self.voice,
            "speed": self.speed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReadingSession":
        return cls(
            session_id=data.get("session_id", str(uuid4())),
            article=data.get("article", ""),
            grade=data.get("grade", 2),
            messages=data.get("messages", []),
            formatted_text=data.get("formatted_text", ""),
            custom_vocab=data.get("custom_vocab", []),
            removed_words=set(data.get("removed_words", [])),
            voice=data.get("voice", ""),
            speed=data.get("speed", 1.0),
            article_id=data.get("article_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class ProjectStore:
    def __init__(self, store_dir: str):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: ReadingSession) -> None:
        filepath = self.store_dir / f"{session.session_id}.json"
        filepath.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, session_id: str) -> Optional[ReadingSession]:
        filepath = self.store_dir / f"{session_id}.json"
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return ReadingSession.from_dict(data)
        except Exception:
            return None

    def delete(self, session_id: str) -> bool:
        filepath = self.store_dir / f"{session_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def list_all(self) -> List[dict]:
        projects = []
        for filepath in sorted(self.store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                projects.append({
                    "session_id": data.get("session_id", filepath.stem),
                    "article_id": data.get("article_id", ""),
                    "title": data.get("article", "")[:40] + "..." if len(data.get("article", "")) > 40 else data.get("article", ""),
                    "updated_at": data.get("updated_at", ""),
                    "created_at": data.get("created_at", ""),
                })
            except Exception:
                continue
        return projects

    def load_all(self) -> Dict[str, ReadingSession]:
        sessions = {}
        for filepath in self.store_dir.glob("*.json"):
            session = self.load(filepath.stem)
            if session:
                sessions[session.session_id] = session
        return sessions


class LocalClaudeClient:
    SYSTEM_PROMPT = (
        "You are a patient English teacher helping a Chinese elementary school student read English short passages. "
        "The student is around second-grade level. Please explain in simple, friendly English. "
        "Only use Chinese when the student explicitly asks for a Chinese translation or explanation. "
        "Be encouraging, gentle when correcting spelling or pronunciation, and avoid long responses. "
        "Do not output emoji."
    )

    def __init__(self, claude_path: Optional[str] = None, cwd: Optional[str] = None):
        self._claude_path = claude_path
        self.cwd = cwd or str(Path(__file__).parent.parent)

    @property
    def claude_path(self) -> str:
        if self._claude_path is None:
            self._claude_path = self._find_claude()
        return self._claude_path

    @staticmethod
    def _find_claude() -> str:
        env_path = os.environ.get("CLAUDE_CODE_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        claude = shutil.which("claude")
        if claude:
            return claude

        local_bin = os.path.expanduser("~/.local/bin/claude")
        if os.path.exists(local_bin):
            return local_bin

        raise RuntimeError(
            "未找到本地 Claude Code CLI。请先安装 Claude Code：\n"
            "  npm install -g @anthropic-ai/claude-code\n"
            "或将 claude 加入 PATH，或设置 CLAUDE_CODE_PATH。"
        )

    def call(
        self,
        messages: List[dict],
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        prompt = self._format_messages(messages)
        cmd = [
            self.claude_path,
            "-p",
            "--system-prompt",
            system_prompt if system_prompt is not None else self.SYSTEM_PROMPT,
            "--no-session-persistence",
            "--output-format",
            "json" if json_schema else "text",
        ]
        if json_schema:
            import json
            cmd.extend(["--json-schema", json.dumps(json_schema, ensure_ascii=False)])

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                cwd=self.cwd,
                env=env,
                creationflags=creationflags,
            )
            if result.returncode == 0:
                output = result.stdout.strip() if result.stdout else ""
                if json_schema and output:
                    import json
                    try:
                        parsed = json.loads(output)
                        if isinstance(parsed, dict) and "text" in parsed:
                            return parsed["text"].strip()
                        return output
                    except json.JSONDecodeError:
                        return output
                return output
            stderr = result.stderr or ""
            raise RuntimeError(f"Claude CLI 返回错误：{stderr[:300]}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI 调用超时")

    def ocr_image(self, image_path: Union[str, Path]) -> str:
        """Use the local Claude CLI to extract text from an image."""
        image_path = str(Path(image_path).resolve())
        prompt = (
            "Extract all English text from this image. "
            "Output only the extracted text, preserving line breaks as they appear. "
            "Do not add any explanation, greeting, or extra content."
        )
        cmd = [
            self.claude_path,
            "-p",
            "--no-session-persistence",
            "--output-format",
            "text",
            f"{prompt} @{image_path}",
        ]
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                cwd=self.cwd,
                env=env,
                creationflags=creationflags,
            )
            if result.returncode == 0:
                return (result.stdout or "").strip()
            stderr = result.stderr or ""
            raise RuntimeError(f"Claude OCR failed: {stderr[:300]}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude OCR call timed out")

    @staticmethod
    def _format_messages(messages: List[dict]) -> str:
        article = ""
        history_lines = []
        current_question = ""

        for i, msg in enumerate(messages):
            role = msg.get("role", "user")
            content = msg.get("content", "").strip()
            if not content:
                continue

            if i == 0 and role == "user":
                article = content
                continue

            if role == "user":
                if i == len(messages) - 1:
                    current_question = content
                else:
                    history_lines.append(f"Student asked: {content}")
            else:
                history_lines.append(f"Teacher answered: {content}")

        parts = ["Please act as an elementary-school English teacher and answer based on the passage below.", "", f"Passage:\n{article}"]
        if history_lines:
            parts.extend(["", "Previous conversation:"])
            parts.extend(history_lines)
        if current_question:
            parts.extend(["", f"Student's current question: {current_question}"])
        else:
            parts.extend(["", "Please greet the student and let them know they can ask you anything."])
        return "\n".join(parts)


class AnthropicClient:
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.system = (
            "You are a patient English teacher helping a Chinese elementary school student read English short passages. "
            "The student is around second-grade level. Please explain in simple, friendly English. "
            "Only use Chinese when the student explicitly asks for a Chinese translation or explanation. "
            "Be encouraging, gentle when correcting spelling or pronunciation, and avoid long responses."
        )

    def call(
        self,
        messages: List[dict],
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt if system_prompt is not None else self.system,
            messages=messages,
        )
        return response.content[0].text.strip()


class ReadingTutor:
    def __init__(self, client=None, model: str = "claude-3-5-sonnet-20241022", project_store: Optional[ProjectStore] = None):
        if client is not None:
            self.client = client
        else:
            self.client = self._create_default_client(model)
        self.project_store = project_store
        self.sessions: dict[str, ReadingSession] = {}
        if self.project_store:
            self.sessions = self.project_store.load_all()

    @staticmethod
    def _create_default_client(model: str):
        try:
            return LocalClaudeClient()
        except RuntimeError:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                return AnthropicClient(api_key=api_key, model=model)
            raise

    def create_session(self, article: str, article_id: str = "", grade: int = 2) -> ReadingSession:
        session_id = str(uuid4())
        article = article.strip()
        formatted_text = self.reparagraph(article)
        session = ReadingSession(
            session_id=session_id,
            article=article,
            grade=grade,
            formatted_text=formatted_text,
            article_id=article_id,
        )
        self.sessions[session_id] = session
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[ReadingSession]:
        return self.sessions.get(session_id)

    def restore_session(self, session_id: str) -> Optional[ReadingSession]:
        if session_id in self.sessions:
            return self.sessions[session_id]
        if self.project_store:
            session = self.project_store.load(session_id)
            if session:
                self.sessions[session_id] = session
            return session
        return None

    def _save_session(self, session: ReadingSession) -> None:
        if self.project_store:
            self.project_store.save(session)

    def _build_messages(self, session: ReadingSession, user_message: Optional[str] = None) -> List[dict]:
        messages = [
            {"role": "user", "content": session.article},
            {
                "role": "assistant",
                "content": "Great! Let's read this passage together. If you see a word you don't know or have any questions, just ask me!",
            },
        ]
        messages.extend(session.messages)
        if user_message:
            messages.append({"role": "user", "content": user_message})
        return messages

    def _call(self, messages: List[dict]) -> str:
        return self.client.call(messages, max_tokens=1024)

    def greet(self, session_id: str) -> str:
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        return "Hi! Let's read this article together. Ask me if you see a word you don't know."

    def ask(self, session_id: str, question: str) -> str:
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        messages = self._build_messages(session, question)
        answer = self._call(messages)
        session.add_message("user", question)
        session.add_message("assistant", answer)
        self._save_session(session)
        return answer


    def translate(self, text: str, context: str = "") -> str:
        prompt = (
            "将下面的英文翻译成中文。"
            "只输出翻译文本本身，不要添加称呼、问候、解释或原文。"
            "把翻译放在 【BEGIN】 和 【END】 标记之间。"
        )
        if context:
            prompt += f"\n\n上下文：\n{context}"
        prompt += f"\n\n需要翻译的英文：\n{text}\n\n中文翻译：\n【BEGIN】\n"
        messages = [{"role": "user", "content": prompt}]
        result = self.client.call(
            messages,
            max_tokens=512,
            system_prompt=(
                "你是一个严格的翻译引擎。只输出用户要求的中文翻译，"
                "绝不添加问候、称呼、解释或任何额外内容。"
                "必须将翻译放在 【BEGIN】 和 【END】 标记之间。"
            ),
        )
        return self._extract_between_markers(result.strip(), "【BEGIN】", "【END】", fallback=text)

    def explain(self, text: str, context: str = "") -> str:
        prompt = (
            f"请用适合小学二年级学生的语言，解释下面这个英语单词或句子的意思。\n\n"
            f"需要解释的内容：\n{text}\n\n"
            "先给出简短中文意思，再用简单英语举个例子。"
        )
        if context:
            prompt = f"上下文：\n{context}\n\n{prompt}"
        messages = [{"role": "user", "content": prompt}]
        return self.client.call(messages, max_tokens=512)

    def reparagraph(self, text: str) -> str:
        prompt = (
            "Reformat the following English text into natural paragraphs based on meaning.\n"
            "Rules:\n"
            "- Do NOT add greetings, introductions, explanations, or any sentence not in the original text.\n"
            "- Do NOT change or delete any sentence.\n"
            "- Put the reformatted text between the markers 【BEGIN】 and 【END】.\n"
            "- Only the text between the markers will be used."
        )
        prompt += f"\n\nText to reformat:\n{text}\n\nReformatted text:\n【BEGIN】\n"
        messages = [{"role": "user", "content": prompt}]
        result = self.client.call(
            messages,
            max_tokens=2048,
            system_prompt=(
                "You are a text formatting tool. You only reformat English text into paragraphs. "
                "You never add greetings, introductions, explanations, or content not in the source text. "
                "You always wrap the output between 【BEGIN】 and 【END】 markers."
            ),
        )
        return self._extract_between_markers(result.strip(), "【BEGIN】", "【END】", fallback=text)

    @staticmethod
    def _extract_between_markers(text: str, start: str, end: str, fallback: str = "") -> str:
        start_idx = text.find(start)
        if start_idx == -1:
            return fallback
        start_idx += len(start)
        end_idx = text.find(end, start_idx)
        if end_idx == -1:
            extracted = text[start_idx:].strip()
        else:
            extracted = text[start_idx:end_idx].strip()
        # If extracted text is empty or only contains non-original content, return fallback
        if not extracted:
            return fallback
        return extracted

    def check_spelling(self, word: str, attempt: str) -> str:
        prompt = (
            f"单词是：{word}\n"
            f"学生写的是：{attempt}\n"
            "请判断拼写是否正确。如果错了，请温柔地指出错误并给出正确拼写。"
            "用适合小学生的简单语言回答。"
        )
        messages = [{"role": "user", "content": prompt}]
        return self.client.call(messages, max_tokens=512)

import asyncio
import logging
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional, Tuple, Dict, Any

from app.config import settings

logger = logging.getLogger("proxy_agy.auth")

# Regex to strip ANSI escape codes
ANSI_ESCAPE_REGEX = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def extract_oauth_url(text: str) -> Optional[str]:
    """
    Extract and reconstruct Google OAuth URL even if line-wrapped across multiple lines.
    """
    # 1. Try cleaned continuous match (handles line-wrapping)
    cleaned = re.sub(r'[\r\n\t ]+', '', text)
    match = re.search(r'https://accounts\.google\.com/o/oauth2/auth\?[a-zA-Z0-9_\-\.%\+&=:]+', cleaned)
    if match:
        return match.group(0)

    # 2. Fallback standard match
    match2 = re.search(r'https://accounts\.google\.com/o/oauth2/auth\?[^\s"\'<>]+', text)
    if match2:
        return match2.group(0).strip()

    return None


class AuthSessionManager:
    """
    Manages interactive OAuth PKCE login sessions for agy CLI.
    Because agy uses PKCE, the code_verifier lives in the running process memory.
    The same process that outputs the OAuth URL must receive the authorization code on stdin.
    """

    def __init__(self):
        self.is_authenticated: bool = False
        self.last_checked_at: float = 0.0
        self.login_message: Optional[str] = None

        # Active login session state
        self.active_proc: Optional[subprocess.Popen] = None
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.current_oauth_url: Optional[str] = None
        self.session_output: str = ""
        self.session_lock = threading.Lock()
        self.url_ready_event = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None

    def probe_auth_sync(self, timeout: int = 20) -> Tuple[bool, Optional[str]]:
        """Probe agy CLI to check if it has valid credentials."""
        agy_bin = settings.AGY_BIN_PATH
        if not os.path.isfile(agy_bin) or not os.access(agy_bin, os.X_OK):
            return False, f"agy binary not found or not executable at {agy_bin}"

        try:
            proc = subprocess.Popen(
                [
                    agy_bin,
                    "-p", "ping",
                    "--output-format", "stream-json",
                    "--model", "Gemini 3.8 Flash (Low)",
                    "--disable-slash-commands",
                    "--dangerously-skip-permissions",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                output = stdout + "\n" + stderr
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                output = stdout + "\n" + stderr

            lower_output = output.lower()

            if "unauthorized" in lower_output or "not logged in" in lower_output or "authentication required" in lower_output or "login required" in lower_output:
                self.is_authenticated = False
                return False, "Authentication required"

            if '{"event":"init"' in output or '"step_update"' in output or '"status":"SUCCESS"' in output or proc.returncode == 0:
                self.is_authenticated = True
                self.last_checked_at = time.time()
                return True, "Authenticated successfully"

            return False, output.strip() or "No response from CLI"

        except Exception as e:
            logger.exception("Error probing agy auth status")
            return False, str(e)

    def close_active_session(self):
        """Terminate and clean up active auth session process."""
        with self.session_lock:
            if self.active_proc:
                try:
                    if self.active_proc.poll() is None:
                        self.active_proc.terminate()
                        time.sleep(0.2)
                        if self.active_proc.poll() is None:
                            self.active_proc.kill()
                except Exception:
                    pass
                self.active_proc = None

            if self.master_fd is not None:
                try:
                    os.close(self.master_fd)
                except Exception:
                    pass
                self.master_fd = None

            if self.slave_fd is not None:
                try:
                    os.close(self.slave_fd)
                except Exception:
                    pass
                self.slave_fd = None

            self.current_oauth_url = None
            self.session_output = ""
            self.url_ready_event.clear()

    def start_auth_session(self) -> Tuple[bool, Optional[str], str]:
        """
        Start an interactive agy CLI process in a pseudo-terminal (PTY).
        Captures the dynamic OAuth2 PKCE authorization URL.
        """
        # First check if already authenticated
        is_auth, _ = self.probe_auth_sync(timeout=8)
        if is_auth:
            self.is_authenticated = True
            return True, "https://antigravity.google", "当前设备已处于已登录状态 (Authenticated)"

        with self.session_lock:
            if self.active_proc and self.active_proc.poll() is None and self.current_oauth_url:
                return True, self.current_oauth_url, "Existing auth session active"

        self.close_active_session()

        agy_bin = settings.AGY_BIN_PATH
        if not os.path.isfile(agy_bin) or not os.access(agy_bin, os.X_OK):
            return False, None, f"agy binary not found at {agy_bin}"

        try:
            master_fd, slave_fd = pty.openpty()
            proc = subprocess.Popen(
                [agy_bin],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                env=os.environ.copy()
            )

            with self.session_lock:
                self.active_proc = proc
                self.master_fd = master_fd
                self.slave_fd = slave_fd
                self.session_output = ""
                self.url_ready_event.clear()

            def read_pty_output():
                buf = ""
                while True:
                    with self.session_lock:
                        m_fd = self.master_fd
                        p = self.active_proc
                    if m_fd is None or p is None or p.poll() is not None:
                        break

                    try:
                        r, _, _ = select.select([m_fd], [], [], 0.5)
                        if r:
                            data = os.read(m_fd, 1024)
                            if not data:
                                break
                            text = data.decode("utf-8", errors="replace")
                            clean_text = ANSI_ESCAPE_REGEX.sub('', text)
                            buf += clean_text
                            with self.session_lock:
                                self.session_output += clean_text

                            # Check for OAuth URL using multi-line extractor
                            extracted_url = extract_oauth_url(buf)
                            if extracted_url and not self.current_oauth_url:
                                with self.session_lock:
                                    self.current_oauth_url = extracted_url
                                logger.info(f"Captured dynamic OAuth URL: {self.current_oauth_url[:60]}...")
                                self.url_ready_event.set()

                    except OSError:
                        break
                    except Exception as e:
                        logger.error(f"Error in pty reader: {e}")
                        break

            self._reader_thread = threading.Thread(target=read_pty_output, daemon=True)
            self._reader_thread.start()

            # Wait up to 8 seconds for the OAuth URL to appear
            ready = self.url_ready_event.wait(timeout=8.0)
            if ready and self.current_oauth_url:
                return True, self.current_oauth_url, "OAuth URL generated successfully"
            elif self.current_oauth_url:
                return True, self.current_oauth_url, "OAuth URL generated"
            else:
                return False, None, f"Timeout waiting for OAuth URL. Output: {self.session_output[-200:]}"

        except Exception as e:
            logger.exception("Failed to start interactive auth session")
            self.close_active_session()
            return False, None, str(e)

    def submit_auth_code(self, code: str) -> Tuple[bool, str]:
        """
        Submit authorization code to the active agy process via PTY stdin.
        """
        code = code.strip()
        if not code:
            return False, "授权码 (Authorization Code) 不能为空"

        with self.session_lock:
            proc = self.active_proc
            master_fd = self.master_fd

        if not proc or proc.poll() is not None or master_fd is None:
            return False, "当前没有正在等待输入的登录会话，请先点击【获取最新登录链接】"

        try:
            logger.info("Writing authorization code to agy CLI stdin...")
            payload = code.encode("utf-8") + b"\n"
            os.write(master_fd, payload)

            # Wait for process to complete token exchange
            start_wait = time.time()
            success = False
            while time.time() - start_wait < 12:
                if proc.poll() is not None:
                    success = (proc.returncode == 0)
                    break
                with self.session_lock:
                    out = self.session_output.lower()
                    if "success" in out or "authenticated" in out or "logged in" in out:
                        success = True
                        break
                time.sleep(0.5)

            self.close_active_session()

            time.sleep(1)
            is_auth, msg = self.probe_auth_sync(timeout=15)
            if is_auth:
                self.is_authenticated = True
                self.login_message = "Logged in successfully"
                return True, "🎉 登录成功！Antigravity CLI 已完成授权激活。"
            else:
                return False, f"授权码已提交，但验证未通过: {msg}"

        except Exception as e:
            logger.exception("Failed to submit auth code")
            self.close_active_session()
            return False, f"提交授权码异常: {str(e)}"

    def run_interactive_terminal_login(self) -> bool:
        """Run terminal-native interactive login."""
        self.close_active_session()
        agy_bin = settings.AGY_BIN_PATH
        print("\n" + "=" * 65)
        print("🔐 [Antigravity CLI] 进入交互式登录引导")
        print("=" * 65)
        print("正在启动 agy 认证流程，若出现登录链接将自动尝试为你打开浏览器...")
        print("完成授权后，请将授权 Code 粘贴在终端中并按回车。\n")

        try:
            subprocess.run([agy_bin], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
            print("\n" + "-" * 65)
            print("正在校验登录结果...")
            is_auth, msg = self.probe_auth_sync(timeout=20)
            if is_auth:
                print("🎉 ✅ 登录成功！Antigravity CLI 已就绪。")
                self.is_authenticated = True
                return True
            else:
                print(f"❌ 登录验证未通过: {msg}")
                self.is_authenticated = False
                return False
        except Exception as e:
            print(f"❌ 启动交互式登录失败: {e}")
            return False


auth_manager = AuthSessionManager()


async def check_auth_async(force_recheck: bool = False) -> bool:
    """Asynchronously check auth state using AuthSessionManager."""
    if not force_recheck and auth_manager.is_authenticated and (time.time() - auth_manager.last_checked_at < 120):
        return True

    loop = asyncio.get_running_loop()
    is_auth, msg = await loop.run_in_executor(None, auth_manager.probe_auth_sync)
    auth_manager.is_authenticated = is_auth
    auth_manager.login_message = msg
    return is_auth

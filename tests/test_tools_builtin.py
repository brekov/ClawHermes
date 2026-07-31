"""tools/builtin.py 工具单元测试 — 补充覆盖率至 85%+

聚焦未覆盖的 handler 分支：异常路径、沙箱回退、httpx mock、
AST 求值器白名单边界、profile 分级注册等。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawhermes.tools.builtin import (
    _base64_codec,
    _calc,
    _calc_eval_node,
    _code_eval,
    _compress_file,
    _csv_parse,
    _delegate_task,
    _disk_usage,
    _exec_command,
    _git_diff,
    _git_log,
    _git_status,
    _grep,
    _hash_file,
    _http_request,
    _image_info,
    _json_query,
    _list_dir,
    _markdown_render,
    _memory_save,
    _memory_search,
    _patch_file,
    _pdf_extract,
    _process_list,
    _read_file,
    _search_replace,
    _sqlite_query,
    _timer,
    _web_fetch,
    _web_search,
    _web_search_duckduckgo,
    _web_search_fallback,
    _web_search_searxng,
    _web_search_serpapi,
    _web_search_tavily,
    _write_file,
    register_builtin_tools,
)

# ============================================================
# 路径校验工具
# ============================================================


class TestPathValidation:
    """_validate_workspace_path / _validate_sqlite_path 边界测试"""

    def test_validate_workspace_path_blocked_system_dir(self):
        """未提供 workspace_root 时系统目录路径应被拒绝"""
        from clawhermes.tools.builtin import _validate_workspace_path

        # 使用 /dev 而非 /etc，避免 macOS 上 /etc→/private/etc 符号链接导致 resolve 后不在 /etc 下
        with pytest.raises(ValueError, match="系统目录"):
            _validate_workspace_path("/dev/null")

    def test_validate_sqlite_path_blocked_system_dir(self):
        """未提供 data_dir 时 SQLite 系统目录路径应被拒绝"""
        from clawhermes.tools.builtin import _validate_sqlite_path

        with pytest.raises(ValueError, match="系统目录"):
            _validate_sqlite_path("/dev/test.db")


# ============================================================
# SQLite / CSV / Hash / Disk / Base64 工具
# ============================================================


class TestDataTools:
    """数据类工具异常与边界测试"""

    def test_sqlite_query_with_params(self, tmp_path):
        """带参数的 SELECT 查询应正确返回结果"""
        db = tmp_path / "t.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t (id INT, name TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'alice')")
        conn.execute("INSERT INTO t VALUES (2, 'bob')")
        conn.commit()
        conn.close()
        result = _sqlite_query(
            db_path=str(db), query="SELECT * FROM t WHERE id = ?", params=[2],
            data_dir=str(tmp_path),
        )
        assert result["count"] == 1
        assert result["rows"][0] == [2, "bob"]

    def test_csv_parse_max_rows_truncation(self, tmp_path):
        """max_rows 应限制返回的行数"""
        f = tmp_path / "data.csv"
        f.write_text("h\n" + "\n".join(f"r{i}" for i in range(10)))
        result = _csv_parse(path=str(f), max_rows=3)
        assert result["count"] == 3

    def test_csv_parse_nonexistent_file(self, tmp_path):
        """读取不存在的 CSV 文件应返回错误"""
        result = _csv_parse(path=str(tmp_path / "nope.csv"))
        assert "error" in result

    def test_hash_file_value_error(self, tmp_path):
        """路径越界时 hash_file 返回 ValueError"""
        result = _hash_file(path="/etc/passwd", workspace_root=str(tmp_path))
        assert "error" in result
        assert "越界" in result["error"]

    def test_hash_file_read_exception(self, tmp_path):
        """读取目录时 hash_file 返回异常错误"""
        result = _hash_file(path=str(tmp_path), workspace_root=str(tmp_path))
        assert "error" in result
        assert "哈希计算失败" in result["error"]

    def test_disk_usage_exception(self):
        """磁盘检查失败时返回错误"""
        with patch("shutil.disk_usage", side_effect=OSError("boom")):
            result = _disk_usage(path="/nonexistent_xyz")
            assert "error" in result
            assert "磁盘检查失败" in result["error"]

    def test_base64_invalid_action(self):
        """不支持的操作应返回错误"""
        result = _base64_codec(action="rot13", text="x")
        assert "error" in result
        assert "不支持的操作" in result["error"]

    def test_base64_decode_exception(self):
        """解码产生非 UTF-8 字节时返回错误"""
        result = _base64_codec(action="decode", text="/8/A")
        assert "error" in result
        assert "Base64 处理失败" in result["error"]


# ============================================================
# 系统工具：process_list / image_info / pdf_extract / markdown_render
# ============================================================


class TestSystemMediaTools:
    """系统与媒体工具的 ImportError / 成功 / 异常路径"""

    def test_process_list_windows(self):
        """Windows 平台应调用 tasklist"""
        with patch("platform.system", return_value="Windows"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="img1.exe\nimg2.exe\n", returncode=0)
            result = _process_list()
            assert result["platform"] == "Windows"
            mock_run.assert_called_once_with(
                ["tasklist"], capture_output=True, text=True, timeout=10,
            )

    def test_process_list_exception(self):
        """subprocess 抛异常时返回错误"""
        with patch("subprocess.run", side_effect=OSError("denied")):
            result = _process_list()
            assert "error" in result
            assert "进程列表获取失败" in result["error"]

    def test_image_info_success(self, tmp_path, monkeypatch):
        """有 Pillow 时正常读取图片信息"""
        fake_img = MagicMock()
        fake_img.format = "PNG"
        fake_img.mode = "RGB"
        fake_img.width = 100
        fake_img.height = 200
        fake_pil = MagicMock()
        fake_pil.Image.open.return_value = fake_img
        monkeypatch.setitem(sys.modules, "PIL", fake_pil)

        f = tmp_path / "test.png"
        f.write_bytes(b"fake png")
        result = _image_info(path=str(f))
        assert result["format"] == "PNG"
        assert result["width"] == 100
        assert result["size_bytes"] == 8

    def test_image_info_exception(self, monkeypatch):
        """Pillow 已安装但图片读取失败"""
        fake_pil = MagicMock()
        fake_pil.Image.open.side_effect = Exception("corrupt")
        monkeypatch.setitem(sys.modules, "PIL", fake_pil)
        result = _image_info(path="/nonexistent.png")
        assert "error" in result
        assert "图片读取失败" in result["error"]

    def test_pdf_extract_success(self, monkeypatch):
        """有 pypdf 时正常提取 PDF 文本"""
        fake_page = MagicMock()
        fake_page.extract_text.return_value = "page text"
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page]
        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader.return_value = fake_reader
        monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

        result = _pdf_extract(path="fake.pdf", max_pages=5)
        assert result["total_pages"] == 1
        assert result["extracted"] == 1
        assert result["pages"][0]["text"] == "page text"

    def test_pdf_extract_empty_page(self, monkeypatch):
        """空文本页面不应出现在结果中"""
        fake_page = MagicMock()
        fake_page.extract_text.return_value = ""
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page]
        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader.return_value = fake_reader
        monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

        result = _pdf_extract(path="fake.pdf")
        assert result["extracted"] == 0

    def test_pdf_extract_exception(self, monkeypatch):
        """pypdf 抛异常时返回错误"""
        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader.side_effect = Exception("parse error")
        monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
        result = _pdf_extract(path="bad.pdf")
        assert "error" in result
        assert "PDF 提取失败" in result["error"]

    def test_markdown_render_with_lib(self, monkeypatch):
        """有 markdown 库时正常渲染"""
        fake_md = MagicMock()
        fake_md.markdown.return_value = "<h1>Title</h1>"
        monkeypatch.setitem(sys.modules, "markdown", fake_md)
        result = _markdown_render(text="# Title")
        assert result["html"] == "<h1>Title</h1>"

    def test_markdown_render_lib_exception(self, monkeypatch):
        """markdown.markdown 抛异常时返回错误"""
        fake_md = MagicMock()
        fake_md.markdown.side_effect = RuntimeError("bad input")
        monkeypatch.setitem(sys.modules, "markdown", fake_md)
        result = _markdown_render(text="# Title")
        assert "error" in result
        assert "Markdown 渲染失败" in result["error"]


# ============================================================
# 文件操作工具
# ============================================================


class TestFileTools:
    """文件操作工具的异常与边界路径"""

    def test_read_file_truncated(self, tmp_path):
        """超过 1MB 的文件应被截断"""
        f = tmp_path / "big.bin"
        f.write_bytes(b"x" * (1024 * 1024 + 100))
        result = _read_file(path=str(f), workspace_root=str(tmp_path))
        assert result["truncated"] is True
        assert result["size"] == 1024 * 1024

    def test_read_file_exception(self, tmp_path):
        """读取目录时返回异常错误"""
        result = _read_file(path=str(tmp_path), workspace_root=str(tmp_path))
        assert "error" in result

    def test_write_file_oversize(self, tmp_path):
        """超过 10MB 的内容应被拒绝"""
        result = _write_file(
            path=str(tmp_path / "big.txt"),
            content="x" * (10 * 1024 * 1024 + 1),
            workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "MB 上限" in result["error"]

    def test_write_file_value_error(self, tmp_path):
        """路径越界时返回 ValueError"""
        result = _write_file(
            path="/etc/exploit.txt", content="x", workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "越界" in result["error"]

    def test_write_file_exception(self, tmp_path):
        """父路径是文件时写入失败"""
        blocker = tmp_path / "blocker"
        blocker.write_text("block")
        target = tmp_path / "blocker" / "sub.txt"
        result = _write_file(
            path=str(target), content="x", workspace_root=str(tmp_path),
        )
        assert "error" in result

    def test_list_dir_exception(self, tmp_path):
        """glob 抛异常时返回错误"""
        with patch.object(Path, "glob", side_effect=OSError("boom")):
            result = _list_dir(path=str(tmp_path))
            assert "error" in result

    def test_patch_file_not_exists(self, tmp_path):
        """文件不存在时 patch 返回错误"""
        result = _patch_file(
            path=str(tmp_path / "nope.txt"), search="a", replace="b",
            workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "文件不存在" in result["error"]

    def test_patch_file_value_error(self, tmp_path):
        """路径越界时 patch 返回 ValueError"""
        result = _patch_file(
            path="/etc/passwd", search="a", replace="b",
            workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "越界" in result["error"]

    def test_search_replace_not_exists(self, tmp_path):
        """文件不存在时 search_replace 返回错误"""
        result = _search_replace(
            path=str(tmp_path / "nope.txt"), search="a", replace="b",
            workspace_root=str(tmp_path),
        )
        assert "error" in result

    def test_search_replace_text_not_found(self, tmp_path):
        """搜索文本不存在时返回错误"""
        f = tmp_path / "f.txt"
        f.write_text("hello world")
        result = _search_replace(
            path=str(f), search="xyz", replace="abc",
            workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "未找到搜索文本" in result["error"]

    def test_search_replace_value_error(self, tmp_path):
        """路径越界时 search_replace 返回 ValueError"""
        result = _search_replace(
            path="/etc/passwd", search="a", replace="b",
            workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "越界" in result["error"]

    def test_grep_path_not_exists(self, tmp_path):
        """路径不存在时 grep 返回错误"""
        result = _grep(pattern="test", path=str(tmp_path / "nonexistent"))
        assert "error" in result
        assert "路径不存在" in result["error"]

    def test_grep_invalid_regex(self, tmp_path):
        """无效正则表达式返回错误"""
        result = _grep(pattern="[unclosed", path=str(tmp_path))
        assert "error" in result
        assert "正则表达式无效" in result["error"]

    def test_grep_skip_dirs(self, tmp_path):
        """应跳过 __pycache__ 等排除目录"""
        (tmp_path / "a.py").write_text("match here\n")
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "b.py").write_text("match in cache\n")
        result = _grep(pattern="match", path=str(tmp_path))
        assert result["count"] == 1
        assert "a.py" in result["matches"][0]

    def test_grep_unreadable_file(self, tmp_path):
        """read_text 抛 OSError 时跳过该文件"""
        (tmp_path / "a.py").write_text("match here\n")
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            result = _grep(pattern="match", path=str(tmp_path))
        assert result["count"] == 0

    def test_grep_fifty_match_limit(self, tmp_path):
        """达到 50 条匹配时应提前返回"""
        f = tmp_path / "many.py"
        f.write_text("\n".join(f"# match_{i}" for i in range(60)))
        result = _grep(pattern="match_", path=str(tmp_path))
        assert result["count"] == 50

    def test_grep_no_matches(self, tmp_path):
        """无匹配时返回空列表"""
        (tmp_path / "a.py").write_text("nothing relevant\n")
        result = _grep(pattern="xyz123", path=str(tmp_path))
        assert result["count"] == 0
        assert result["matches"] == []

    def test_compress_file_not_exists(self, tmp_path):
        """源文件不存在时返回错误"""
        result = _compress_file(
            path=str(tmp_path / "nope.txt"), workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "文件不存在" in result["error"]

    def test_compress_file_with_output(self, tmp_path):
        """指定输出路径时压缩到指定位置"""
        src = tmp_path / "src.txt"
        src.write_text("compress me " * 50)
        dst = tmp_path / "out.gz"
        result = _compress_file(
            path=str(src), output=str(dst), workspace_root=str(tmp_path),
        )
        assert result["success"] is True
        assert Path(result["output"]).exists()

    def test_compress_file_value_error(self, tmp_path):
        """输出路径越界时返回 ValueError"""
        src = tmp_path / "src.txt"
        src.write_text("data")
        result = _compress_file(
            path=str(src), output="/etc/out.gz", workspace_root=str(tmp_path),
        )
        assert "error" in result
        assert "越界" in result["error"]

    def test_compress_file_read_exception(self, tmp_path):
        """源路径是目录时读取失败"""
        result = _compress_file(
            path=str(tmp_path), workspace_root=str(tmp_path),
        )
        assert "error" in result


# ============================================================
# 代码执行 / Shell 工具
# ============================================================


class TestExecAndCodeEval:
    """_exec_command / _code_eval 的沙箱路径与异常回退"""

    def test_exec_command_sandbox_success(self):
        """Docker 沙箱可用时通过沙箱执行命令"""
        from clawhermes.tools.sandbox import SandboxResult

        with patch("clawhermes.tools.sandbox.DockerSandbox") as mock_sandbox:
            mock_sandbox.is_available.return_value = True
            mock_sandbox.return_value.run_command.return_value = SandboxResult(
                exit_code=0, stdout="hello\n", stderr="", duration_ms=10,
            )
            result = _exec_command(command="echo hello")
            assert result["sandbox"] is True
            assert result["return_code"] == 0
            assert "hello" in result["stdout"]

    def test_exec_command_sandbox_exit_neg1_fallback(self):
        """沙箱 exit_code=-1 时回退到 subprocess"""
        from clawhermes.tools.sandbox import SandboxResult

        with patch("clawhermes.tools.sandbox.DockerSandbox") as mock_sandbox:
            mock_sandbox.is_available.return_value = True
            mock_sandbox.return_value.run_command.return_value = SandboxResult(
                exit_code=-1, stdout="", stderr="err", duration_ms=10,
            )
            result = _exec_command(command="echo hi")
            assert result["sandbox"] is False

    def test_exec_command_sandbox_exception_fallback(self):
        """沙箱导入/实例化抛异常时回退到 subprocess"""
        with patch("clawhermes.tools.sandbox.DockerSandbox") as mock_sandbox:
            mock_sandbox.is_available.side_effect = Exception("import broke")
            result = _exec_command(command="echo hi")
            assert result["sandbox"] is False

    def test_exec_command_subprocess_exception(self):
        """subprocess 抛非超时异常时返回错误"""
        with patch("clawhermes.tools.sandbox.DockerSandbox.is_available", return_value=False), \
             patch("clawhermes.tools.builtin.subprocess.run", side_effect=OSError("boom")):
            result = _exec_command(command="echo hi")
            assert "error" in result
            assert "boom" in result["error"]

    def test_code_eval_sandbox_success(self):
        """Docker 沙箱可用时通过沙箱执行代码"""
        from clawhermes.tools.sandbox import SandboxResult

        with patch("clawhermes.tools.sandbox.DockerSandbox") as mock_sandbox:
            mock_sandbox.is_available.return_value = True
            mock_sandbox.return_value.run_python.return_value = SandboxResult(
                exit_code=0, stdout="5\n", stderr="", duration_ms=10,
            )
            result = _code_eval(code="print(2+3)")
            assert result["sandbox"] is True
            assert result["return_code"] == 0

    def test_code_eval_sandbox_exit_neg1_fallback(self):
        """沙箱 exit_code=-1 时回退到 subprocess"""
        from clawhermes.tools.sandbox import SandboxResult

        with patch("clawhermes.tools.sandbox.DockerSandbox") as mock_sandbox:
            mock_sandbox.is_available.return_value = True
            mock_sandbox.return_value.run_python.return_value = SandboxResult(
                exit_code=-1, stdout="", stderr="err", duration_ms=10,
            )
            result = _code_eval(code="print(1)")
            assert result["sandbox"] is False

    def test_code_eval_sandbox_exception_fallback(self):
        """沙箱抛异常时回退到 subprocess"""
        with patch("clawhermes.tools.sandbox.DockerSandbox") as mock_sandbox:
            mock_sandbox.is_available.side_effect = Exception("broke")
            result = _code_eval(code="print(1)")
            assert result["sandbox"] is False

    def test_code_eval_subprocess_exception(self):
        """subprocess 抛非超时异常时返回错误"""
        with patch("clawhermes.tools.sandbox.DockerSandbox.is_available", return_value=False), \
             patch("clawhermes.tools.builtin.subprocess.run", side_effect=OSError("boom")):
            result = _code_eval(code="print(1)")
            assert "error" in result


# ============================================================
# 网络搜索工具
# ============================================================


def _mock_httpx_response(text: str = "", json_data: dict | None = None):
    """构造 mock httpx 响应对象"""
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


class TestWebSearchDispatch:
    """_web_search 引擎分发与异常路径"""

    def test_dispatch_to_searxng(self, monkeypatch):
        """CH_SEARCH_ENGINE=searxng 时分发到 searxng"""
        monkeypatch.setenv("CH_SEARCH_ENGINE", "searxng")
        with patch("clawhermes.tools.builtin._web_search_searxng", return_value={"engine": "searxng"}) as m:
            result = _web_search("test")
            assert result["engine"] == "searxng"
            m.assert_called_once_with("test")

    def test_dispatch_to_serpapi(self, monkeypatch):
        """CH_SEARCH_ENGINE=serpapi 时分发到 serpapi"""
        monkeypatch.setenv("CH_SEARCH_ENGINE", "serpapi")
        with patch("clawhermes.tools.builtin._web_search_serpapi", return_value={"engine": "serpapi"}) as m:
            result = _web_search("test")
            assert result["engine"] == "serpapi"
            m.assert_called_once_with("test")

    def test_dispatch_to_tavily(self, monkeypatch):
        """CH_SEARCH_ENGINE=tavily 时分发到 tavily"""
        monkeypatch.setenv("CH_SEARCH_ENGINE", "tavily")
        with patch("clawhermes.tools.builtin._web_search_tavily", return_value={"engine": "tavily"}) as m:
            result = _web_search("test")
            assert result["engine"] == "tavily"
            m.assert_called_once_with("test")

    def test_dispatch_exception(self, monkeypatch):
        """分发函数抛异常时 _web_search 返回错误"""
        monkeypatch.setenv("CH_SEARCH_ENGINE", "duckduckgo")
        with patch("clawhermes.tools.builtin._web_search_duckduckgo", side_effect=RuntimeError("boom")):
            result = _web_search("test")
            assert "error" in result
            assert "boom" in result["error"]


class TestWebSearchDuckDuckGo:
    """_web_search_duckduckgo 的 ImportError / 空结果 / 异常回退"""

    def test_duckduckgo_import_error(self, monkeypatch):
        """httpx 未安装时回退到 fallback"""
        monkeypatch.setitem(sys.modules, "httpx", None)
        result = _web_search_duckduckgo("test")
        assert isinstance(result, dict)

    def test_duckduckgo_empty_results(self):
        """搜索结果为空时返回 note"""
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(text="<html><body></body></html>")
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            result = _web_search_duckduckgo("test")
            assert "note" in result or result.get("count", 0) == 0

    def test_duckduckgo_http_error_fallback(self):
        """httpx 请求失败时回退到 fallback"""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("conn fail")
            result = _web_search_duckduckgo("test")
            assert "engine" in result or "error" in result


class TestWebSearchSearxng:
    """_web_search_searxng 的 ImportError / 成功 / 异常路径"""

    def test_searxng_import_error(self, monkeypatch):
        """httpx 未安装时返回错误"""
        monkeypatch.setitem(sys.modules, "httpx", None)
        result = _web_search_searxng("test")
        assert "error" in result
        assert "httpx 未安装" in result["error"]

    def test_searxng_success(self):
        """SearXNG 返回 JSON 时正常解析结果"""
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(json_data={
                "results": [
                    {"title": "T1", "url": "http://u1", "content": "C1"},
                    {"title": "T2", "url": "http://u2", "content": "C2"},
                ],
            })
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            result = _web_search_searxng("test")
            assert result["engine"] == "searxng"
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "T1"

    def test_searxng_connection_failure(self):
        """SearXNG 连接失败时返回错误"""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("conn fail")
            result = _web_search_searxng("test")
            assert "error" in result
            assert "SearXNG 连接失败" in result["error"]


class TestWebSearchSerpapi:
    """_web_search_serpapi 的 ImportError / 成功路径"""

    def test_serpapi_import_error(self, monkeypatch):
        """httpx 未安装时返回错误"""
        monkeypatch.setenv("CH_SERPAPI_KEY", "fake-key")
        monkeypatch.setitem(sys.modules, "httpx", None)
        result = _web_search_serpapi("test")
        assert "error" in result
        assert "httpx 未安装" in result["error"]

    def test_serpapi_success(self, monkeypatch):
        """设置 API key 且 httpx 正常时返回结果"""
        monkeypatch.setenv("CH_SERPAPI_KEY", "fake-key")
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(json_data={
                "organic_results": [
                    {"title": "T1", "link": "http://u1", "snippet": "S1"},
                ],
            })
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            result = _web_search_serpapi("test")
            assert result["engine"] == "serpapi"
            assert result["results"][0]["title"] == "T1"


class TestWebSearchTavily:
    """_web_search_tavily 的 ImportError / 成功路径"""

    def test_tavily_import_error(self, monkeypatch):
        """httpx 未安装时返回错误"""
        monkeypatch.setenv("CH_TAVILY_KEY", "fake-key")
        monkeypatch.setitem(sys.modules, "httpx", None)
        result = _web_search_tavily("test")
        assert "error" in result
        assert "httpx 未安装" in result["error"]

    def test_tavily_success(self, monkeypatch):
        """设置 API key 且 httpx 正常时返回结果"""
        monkeypatch.setenv("CH_TAVILY_KEY", "fake-key")
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(json_data={
                "results": [
                    {"title": "T1", "url": "http://u1", "content": "C1"},
                ],
            })
            mock_client.return_value.__enter__.return_value.post.return_value = resp
            result = _web_search_tavily("test")
            assert result["engine"] == "tavily"
            assert result["results"][0]["title"] == "T1"


class TestWebSearchFallback:
    """_web_search_fallback 的 ImportError / 成功 / 异常路径"""

    def test_fallback_import_error(self, monkeypatch):
        """httpx 未安装时返回 note"""
        monkeypatch.setitem(sys.modules, "httpx", None)
        result = _web_search_fallback("test")
        assert "note" in result
        assert "httpx 未安装" in result["note"]

    def test_fallback_success(self):
        """Google fallback 成功解析 h3 标题"""
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(
                text="<html><h3>Result 1</h3><h3>Result 2</h3></html>",
            )
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            result = _web_search_fallback("test")
            assert result["engine"] == "google_fallback"
            assert len(result["results"]) == 2

    def test_fallback_request_error(self):
        """Google fallback 请求失败时返回 note"""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("conn fail")
            result = _web_search_fallback("test")
            assert "note" in result
            assert "搜索请求失败" in result["note"]

    def test_fallback_empty_results(self):
        """Google fallback 无 h3 时返回空结果"""
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(text="<html><body>no h3 here</body></html>")
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            result = _web_search_fallback("test")
            assert result["results"] == []


class TestWebFetch:
    """_web_fetch 的 ImportError / HTTPError / 成功 / 空内容路径"""

    def test_web_fetch_import_error(self, monkeypatch):
        """httpx 未安装时返回错误"""
        monkeypatch.setitem(sys.modules, "httpx", None)
        result = _web_fetch(url="http://example.com")
        assert "error" in result
        assert "httpx 未安装" in result["error"]

    def test_web_fetch_http_error(self):
        """HTTP 请求失败时返回错误"""
        import httpx

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.HTTPError("bad")
            result = _web_fetch(url="http://example.com")
            assert "error" in result
            assert "HTTP 请求失败" in result["error"]

    def test_web_fetch_generic_exception(self):
        """非 HTTPError 异常时返回错误"""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = RuntimeError("boom")
            result = _web_fetch(url="http://example.com")
            assert "error" in result
            assert "boom" in result["error"]

    def test_web_fetch_success_strips_tags(self):
        """成功抓取时应剥离 script/style/HTML 标签"""
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(
                text="<html><script>x()</script><style>.a{}</style><p>Hello World</p></html>",
            )
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            result = _web_fetch(url="http://example.com")
            assert "Hello World" in result["content"]
            assert "<script>" not in result["content"]
            assert "<style>" not in result["content"]
            assert "<p>" not in result["content"]

    def test_web_fetch_empty_content(self):
        """抓取内容全为空白时返回空内容提示"""
        with patch("httpx.Client") as mock_client:
            resp = _mock_httpx_response(text="<html>   \n  </html>")
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            result = _web_fetch(url="http://example.com")
            assert result["content"] == "（内容为空）"


class TestHttpRequest:
    """_http_request 异常路径"""

    def test_http_request_exception(self):
        """httpx 请求抛异常时返回错误"""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.request.side_effect = Exception("conn fail")
            result = _http_request(url="http://example.com", method="GET")
            assert "error" in result
            assert "HTTP 请求失败" in result["error"]


# ============================================================
# 记忆 / 委派工具
# ============================================================


class TestMemoryAndDelegate:
    """_memory_search / _memory_save / _delegate_task 有 manager 时的路径"""

    def test_memory_search_with_manager(self):
        """有 memory_manager 时正常搜索返回结果"""
        manager = MagicMock()
        item = MagicMock()
        item.content = "test memory"
        item.importance = 0.8
        manager.search.return_value = [item]
        result = _memory_search(query="test", _memory_manager=manager)
        assert result["results"][0]["content"] == "test memory"
        assert result["results"][0]["importance"] == 0.8

    def test_memory_search_manager_exception(self):
        """manager.search 抛异常时返回错误"""
        manager = MagicMock()
        manager.search.side_effect = Exception("search fail")
        result = _memory_search(query="test", _memory_manager=manager)
        assert "error" in result

    def test_memory_save_with_manager(self):
        """有 memory_manager 时正常保存"""
        manager = MagicMock()
        result = _memory_save(content="test", _memory_manager=manager)
        assert result["success"] is True

    def test_memory_save_manager_exception(self):
        """manager.save 抛异常时返回错误"""
        manager = MagicMock()
        manager.save.side_effect = Exception("save fail")
        result = _memory_save(content="test", _memory_manager=manager)
        assert "error" in result

    def test_delegate_task_with_manager(self):
        """有 delegate_manager 时正常委派"""
        manager = MagicMock()
        manager.delegate.return_value = [{"task_id": "t1", "result": "done"}]
        result = _delegate_task(
            tasks=[{"id": "t1", "description": "test"}],
            _delegate_manager=manager,
        )
        assert "results" in result
        assert result["results"][0]["task_id"] == "t1"

    def test_delegate_task_manager_exception(self):
        """manager.delegate 抛异常时返回错误"""
        manager = MagicMock()
        manager.delegate.side_effect = Exception("delegate fail")
        result = _delegate_task(tasks=[{"id": "t1"}], _delegate_manager=manager)
        assert "error" in result


# ============================================================
# JSON 查询 / Git / Timer 工具
# ============================================================


class TestJsonQuery:
    """_json_query 的无路径 / 类型错误 / 解析失败路径"""

    def test_json_query_no_path(self):
        """不提供 path 时返回完整数据"""
        result = _json_query(json_str='{"a": 1, "b": 2}')
        assert result["result"] == {"a": 1, "b": 2}

    def test_json_query_non_container_access(self):
        """访问非容器类型的路径时返回错误"""
        result = _json_query(json_str="42", path="a")
        assert "error" in result
        assert "不是容器类型" in result["error"]

    def test_json_query_decode_error(self):
        """JSON 解析失败时返回错误"""
        result = _json_query(json_str="invalid json", path="a")
        assert "error" in result
        assert "JSON 解析失败" in result["error"]

    def test_json_query_key_error(self):
        """路径键不存在时返回错误"""
        result = _json_query(json_str='{"a": 1}', path="b")
        assert "error" in result
        assert "路径查询失败" in result["error"]

    def test_json_query_index_value_error(self):
        """列表索引非数字时返回错误"""
        result = _json_query(json_str='[1, 2, 3]', path="x")
        assert "error" in result

    def test_json_query_generic_exception(self):
        """json.loads 抛非标准异常时返回错误"""
        with patch("clawhermes.tools.builtin.json.loads", side_effect=TypeError("bad")):
            result = _json_query(json_str="{}", path="a")
            assert "error" in result


class TestGitTools:
    """_git_status / _git_diff / _git_log 异常与 staged 路径"""

    def test_git_status_exception(self, tmp_path):
        """git status 执行异常时返回错误"""
        with patch("clawhermes.tools.builtin.subprocess.run", side_effect=OSError("git not found")):
            result = _git_status(path=str(tmp_path))
            assert "error" in result

    def test_git_diff_staged(self, tmp_path):
        """staged=True 时查看暂存区差异"""
        mock_result = MagicMock()
        mock_result.stdout = "diff --git a/file b/file\n+added"
        with patch("clawhermes.tools.builtin.subprocess.run", return_value=mock_result) as mock_run:
            result = _git_diff(path=str(tmp_path), staged=True)
            assert "diff" in result
            args = mock_run.call_args[0][0]
            assert "--staged" in args

    def test_git_diff_exception(self, tmp_path):
        """git diff 执行异常时返回错误"""
        with patch("clawhermes.tools.builtin.subprocess.run", side_effect=OSError("fail")):
            result = _git_diff(path=str(tmp_path))
            assert "error" in result

    def test_git_log_exception(self, tmp_path):
        """git log 执行异常时返回错误"""
        with patch("clawhermes.tools.builtin.subprocess.run", side_effect=OSError("fail")):
            result = _git_log(path=str(tmp_path))
            assert "error" in result


class TestTimer:
    """_timer 的 elapsed / 未知操作路径"""

    def test_timer_elapsed_not_found(self):
        """查询不存在的计时器返回错误"""
        result = _timer(action="elapsed", timer_id="nonexistent_timer_xyz")
        assert "error" in result
        assert "计时器不存在" in result["error"]

    def test_timer_elapsed_no_id(self):
        """elapsed 不提供 timer_id 时返回错误"""
        result = _timer(action="elapsed")
        assert "error" in result

    def test_timer_start_then_elapsed(self):
        """启动计时器后查询已用时间"""
        start_result = _timer(action="start", timer_id="test_timer_abc")
        assert start_result["action"] == "started"
        assert start_result["timer_id"] == "test_timer_abc"
        elapsed_result = _timer(action="elapsed", timer_id="test_timer_abc")
        assert elapsed_result["action"] == "elapsed"
        assert "seconds" in elapsed_result
        assert elapsed_result["seconds"] >= 0

    def test_timer_unknown_action(self):
        """未知操作返回错误"""
        result = _timer(action="pause")
        assert "error" in result
        assert "未知操作" in result["error"]


# ============================================================
# 安全表达式求值器 _calc / _calc_eval_node
# ============================================================


class TestCalcEvaluator:
    """_calc_eval_node 白名单边界与 _calc 异常路径"""

    def test_calc_string_constant_rejected(self):
        """字符串常量应被拒绝"""
        result = _calc(expression='"hello"')
        assert "error" in result
        assert "不允许的常量类型" in result["error"]

    def test_calc_unsupported_binop(self):
        """不支持的二元运算（如位移）应被拒绝"""
        result = _calc(expression="1 << 2")
        assert "error" in result
        assert "不允许的二元运算" in result["error"]

    def test_calc_unary_op_success(self):
        """合法一元运算（负号）应正常求值"""
        result = _calc(expression="-5")
        assert result["result"] == -5

    def test_calc_unsupported_unaryop(self):
        """不支持的一元运算（如按位取反）应被拒绝"""
        result = _calc(expression="~1")
        assert "error" in result
        assert "不允许的一元运算" in result["error"]

    def test_calc_disallowed_name(self):
        """不在白名单中的名字应被拒绝"""
        result = _calc(expression="foo")
        assert "error" in result
        assert "不允许的名字" in result["error"]

    def test_calc_keywords_rejected(self):
        """关键字参数应被拒绝"""
        result = _calc(expression="abs(x=1)")
        assert "error" in result
        assert "不支持关键字参数" in result["error"]

    def test_calc_disallowed_func(self):
        """不在白名单中的函数应被拒绝"""
        result = _calc(expression="eval('1')")
        assert "error" in result
        assert "不允许的函数" in result["error"]

    def test_calc_unknown_node_type(self):
        """不支持的语法节点（如列表）应被拒绝"""
        result = _calc(expression="[1, 2, 3]")
        assert "error" in result
        assert "不允许的语法节点" in result["error"]

    def test_calc_syntax_error(self):
        """语法错误时返回计算失败"""
        result = _calc(expression="2 +")
        assert "error" in result
        assert "计算失败" in result["error"]

    def test_calc_eval_node_expression_wrapper(self):
        """_calc_eval_node 直接调用应正确求值 Expression 节点"""
        import ast

        tree = ast.parse("1 + 2", mode="eval")
        assert _calc_eval_node(tree) == 3

    def test_calc_eval_node_constant(self):
        """_calc_eval_node 对数字常量直接返回"""
        import ast

        node = ast.Constant(value=42)
        assert _calc_eval_node(node) == 42

    def test_calc_eval_node_complex_constant(self):
        """_calc_eval_node 对复数常量直接返回"""
        import ast

        node = ast.Constant(value=3 + 4j)
        assert _calc_eval_node(node) == 3 + 4j


# ============================================================
# register_builtin_tools profile 分级
# ============================================================


class TestRegisterBuiltinTools:
    """register_builtin_tools 的 profile 分级注册"""

    def test_register_full_profile_includes_all(self):
        """full profile 应注册全部 FULL_TOOLS 工具"""
        from clawhermes.tools.builtin import FULL_TOOLS
        from clawhermes.tools.registry import ToolRegistry

        registry = ToolRegistry()
        register_builtin_tools(registry, profile="full")
        names = {t.name for t in registry.list()}
        assert names == FULL_TOOLS

    def test_register_unknown_profile_defaults_to_standard(self):
        """未知 profile 应回退到 standard"""
        from clawhermes.tools.builtin import STANDARD_TOOLS
        from clawhermes.tools.registry import ToolRegistry

        registry = ToolRegistry()
        register_builtin_tools(registry, profile="nonexistent")
        names = {t.name for t in registry.list()}
        assert names == STANDARD_TOOLS

    def test_register_minimal_profile(self):
        """minimal profile 应注册 MINIMAL_TOOLS"""
        from clawhermes.tools.builtin import MINIMAL_TOOLS
        from clawhermes.tools.registry import ToolRegistry

        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        names = {t.name for t in registry.list()}
        assert names == MINIMAL_TOOLS

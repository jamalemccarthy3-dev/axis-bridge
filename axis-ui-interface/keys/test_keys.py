import json
import threading
import urllib.error
import urllib.request

import pytest

import server as ks

SECRET = "sk-ant-api03-THISISAVERYSECRETVALUE"


@pytest.fixture
def tool(tmp_path, monkeypatch):
    ui = tmp_path / "ui"
    (ui / "keys").mkdir(parents=True)
    blog = ui / "blog"; blog.mkdir()
    (blog / "module.json").write_text(json.dumps({"name": "blog", "title": "The Blog", "keys": [
        {"name": "BG_ANTHROPIC_KEY", "label": "Anthropic", "prefix": ["sk-ant-"], "restart": True},
        {"name": "BG_SMTP_HOST", "label": "SMTP host", "secret": False},
        {"name": "lower_case_is_rejected", "label": "bad"},
    ]}))
    (blog / ".env").write_bytes(b"# settings\r\nBG_ADMIN_TOKEN=keepme\r\nBG_ANTHROPIC_KEY=\r\nBG_SMTP_HOST=smtp.old.com\r\n")
    away = tmp_path / "elsewhere"; away.mkdir()                                  # a module that lives outside the UI folder, via a pointer
    (away / "module.json").write_text(json.dumps({"name": "picthis", "title": "PICTHIS", "keys": [{"name": "HF_TOKEN", "label": "HF", "prefix": ["hf_"]}]}))
    (ui / "picthis.module.json").write_text(json.dumps({"folder": str(away).replace("\\", "/")}))
    plain = ui / "nokeys"; plain.mkdir(); (plain / "module.json").write_text(json.dumps({"name": "nokeys"}))
    monkeypatch.setattr(ks, "UI_DIR", str(ui)); monkeypatch.setattr(ks, "HERE", str(ui / "keys"))
    srv = ks.make_server(p=0)
    monkeypatch.setenv("KEYS_PORT", str(srv.server_address[1]))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield type("T", (), {"url": f"http://127.0.0.1:{srv.server_address[1]}", "blog": blog, "away": away})
    srv.shutdown()


def call(tool, method, path, body=None, headers=None, token=True):
    h = {"Content-Type": "application/json", **({"X-Keys-Token": ks.TOKEN} if token and method == "POST" else {}), **(headers or {})}
    req = urllib.request.Request(tool.url + path, data=None if body is None else json.dumps(body).encode(), method=method, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw.decode())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode()


def test_it_lists_only_declared_keys_from_folders_and_pointers_and_never_shows_secrets(tool):
    mods = {m["name"]: m for m in call(tool, "GET", "/api/keys")[1]["modules"]}
    assert set(mods) == {"blog", "picthis"}                                            # "nokeys" declares none; "keys" is itself skipped
    assert [k["name"] for k in mods["blog"]["keys"]] == ["BG_ANTHROPIC_KEY", "BG_SMTP_HOST"]    # the lower-case name is refused
    anth, smtp = mods["blog"]["keys"]
    assert anth["set"] is False and anth["value"] is None and smtp["set"] is True and smtp["value"] == "smtp.old.com"


def test_saving_writes_only_that_line_in_that_modules_env_and_never_echoes_the_value(tool):
    st, d = call(tool, "POST", "/api/keys/save", {"module": "blog", "name": "BG_ANTHROPIC_KEY", "value": "  " + SECRET + "  "})
    assert st == 200 and d == {"ok": True, "set": True, "restart": True} and SECRET not in json.dumps(d)
    text = (tool.blog / ".env").read_bytes().decode()
    assert text == f"# settings\r\nBG_ADMIN_TOKEN=keepme\r\nBG_ANTHROPIC_KEY={SECRET}\r\nBG_SMTP_HOST=smtp.old.com\r\n"       # CRLF and other lines untouched
    assert SECRET not in json.dumps(call(tool, "GET", "/api/keys")[1])                                                 # the list shows only "set"
    assert [k for m in call(tool, "GET", "/api/keys")[1]["modules"] for k in m["keys"] if k["name"] == "BG_ANTHROPIC_KEY"][0]["set"] is True
    assert not (tool.blog / ".env.tmp").exists()


def test_a_new_key_is_appended_and_a_pointer_module_gets_its_own_file(tool):
    assert call(tool, "POST", "/api/keys/save", {"module": "picthis", "name": "HF_TOKEN", "value": "hf_abc123"})[0] == 200
    assert (tool.away / ".env").read_text().strip() == "HF_TOKEN=hf_abc123"
    assert call(tool, "POST", "/api/keys/save", {"module": "blog", "name": "BG_SMTP_HOST", "value": "smtp.new.com"})[0] == 200
    assert "BG_SMTP_HOST=smtp.new.com" in (tool.blog / ".env").read_text() and "smtp.old.com" not in (tool.blog / ".env").read_text()


def test_clearing_and_bad_values_are_handled(tool):
    call(tool, "POST", "/api/keys/save", {"module": "blog", "name": "BG_ANTHROPIC_KEY", "value": SECRET})
    assert call(tool, "POST", "/api/keys/save", {"module": "blog", "name": "BG_ANTHROPIC_KEY", "value": ""})[1]["set"] is False
    for bad in ("wrong-prefix-value", SECRET + "\nBG_ADMIN_TOKEN=pwned", '"' + SECRET + '"', "x" * 500):
        st, d = call(tool, "POST", "/api/keys/save", {"module": "blog", "name": "BG_ANTHROPIC_KEY", "value": bad})
        assert st == 400 and bad not in json.dumps(d), bad[:20]
    assert "pwned" not in (tool.blog / ".env").read_text() and "BG_ADMIN_TOKEN=keepme" in (tool.blog / ".env").read_text()


def test_it_can_only_write_declared_settings_to_known_modules(tool):
    for body in ({"module": "blog", "name": "BG_ADMIN_TOKEN", "value": "x"},            # not declared by the module
                 {"module": "blog", "name": "../../etc", "value": "x"},
                 {"module": "ghost", "name": "BG_ANTHROPIC_KEY", "value": "sk-ant-x"},
                 {"module": "../blog", "name": "BG_ANTHROPIC_KEY", "value": "sk-ant-x"},
                 {"module": "nokeys", "name": "BG_ANTHROPIC_KEY", "value": "sk-ant-x"}):
        assert call(tool, "POST", "/api/keys/save", body)[0] == 404, body
    assert "keepme" in (tool.blog / ".env").read_text()


def test_this_computer_only_with_a_per_run_token_and_no_cross_site_posts(tool):
    ok = {"module": "blog", "name": "BG_SMTP_HOST", "value": "h.example.com"}
    assert call(tool, "POST", "/api/keys/save", ok, token=False)[0] == 403                                  # no token
    assert call(tool, "POST", "/api/keys/save", ok, headers={"X-Keys-Token": "guess"}, token=False)[0] == 403
    assert call(tool, "POST", "/api/keys/save", ok, headers={"Origin": "http://evil.example.com"})[0] == 403
    assert call(tool, "GET", "/api/keys", headers={"Host": "evil.example.com"})[0] == 404                   # unknown host name
    assert call(tool, "GET", "/api/keys", headers={"X-Forwarded-For": "8.8.8.8"})[0] == 404                 # came through a proxy or tunnel
    assert call(tool, "GET", "/")[0] == 200 and ks.TOKEN in call(tool, "GET", "/")[1]
    assert "smtp.old.com" in (tool.blog / ".env").read_text()


def test_removing_a_module_removes_its_keys_from_the_page(tool, tmp_path):
    (tool.blog / "module.json").unlink()
    assert {m["name"] for m in call(tool, "GET", "/api/keys")[1]["modules"]} == {"picthis"}

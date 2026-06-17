# Contributing

欢迎贡献 ClawHermes！

## 贡献方式

- **提 Issue**：功能建议、Bug 报告
- **提交 PR**：代码贡献
- **完善文档**：修复错别字、补充说明
- **贡献渠道适配器**：实现 `ChannelAdapter` ABC 即可接入新平台
- **贡献技能**：通过 SkillHub 发布到技能仓库

## 开发环境

见 [docs/development.md](docs/development.md)。

## PR 规范

1. 从 `main` 分支切出 feature 分支（如 `feature/phase3-skill-evolution`）
2. 提交前确保全部检查通过：
   ```bash
   ruff check src/ tests/
   mypy src/
   pytest tests/ -v
   ```
3. 提交信息格式：`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`
4. PR 描述中说明改动内容和测试情况

## 代码规范

- Python 3.12+
- 类型注解全覆盖（mypy 6 项严格检查，零 `typing.Any`）
- ruff lint
- 单文件不超过 500 行
- `json.loads()` 使用 `assert isinstance()` 做运行时守卫

## 添加新工具

1. 在 `tools/builtin.py` 中实现 handler，更新 `FULL_TOOLS` 集合
2. 在 `register_builtin_tools()` 中注册 `ToolDef`
3. 标记 `parallel_safe` / `require_confirm` 属性
4. 在 `tests/test_unit_extended.py` 中添加测试

## 发布流程

```bash
# 1. 更新版本号
# pyproject.toml: version = "0.x.0"

# 2. 更新 CHANGELOG.md

# 3. 提交 + 打 tag
git add -A && git commit -m "release: v0.x.0"
git tag -a v0.x.0 -m "v0.x.0"
git push origin main --tags

# 4. 创建 GitHub Release
gh release create v0.x.0 --title "v0.x.0" --notes-file RELEASE.md
```

## License

MIT

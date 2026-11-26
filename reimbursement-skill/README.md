# 月度个人报销技能

这是一个供团队共用的 Codex 技能。它按当期报销清单核对发票、补录 Excel、汇总金额，并按主体生成包含发票 PDF 和高速费行程单的 ZIP。

## 首次使用

1. 获取仓库并进入存放本说明的目录。把 [技能目录](skills/monthly-personal-reimbursement/) 整个复制到本机的 `$CODEX_HOME/skills/`。未设置 `CODEX_HOME` 时用 `~/.codex/skills/`。最终应能找到 `skills/monthly-personal-reimbursement/SKILL.md`。
2. 按 [个人配置指南](skills/monthly-personal-reimbursement/references/local-profile.md) 复制并填写 [示例配置](examples/reimbursement-profile.example.json)。填写自己的台账路径、报销目录、主体和购方名称。需要查邮件时，在同一份本机配置中填写邮箱。
3. 在 Codex 中使用 `$monthly-personal-reimbursement`，或说「帮我做这个月报销，核对发票、更新台账，再按主体打包」。只需分包时，可以说「按我刚更新的报销表，只把发票齐全的项目分主体打包」。

当期要用的工作簿、目标目录、报销范围和分组以这次的要求为准。缺票时会列出项目与金额，便于补齐。团队更新仓库后，可以重新复制技能目录来更新，本机的个人配置放在单独的 `profiles/` 目录中。

## 文件与验证

- [SKILL.md](skills/monthly-personal-reimbursement/SKILL.md) 包含报销流程和核验口径。
- [打包说明](skills/monthly-personal-reimbursement/references/packaging.md) 说明如何使用 Python 3.9 及以上版本，按已核实的清单生成和校验 ZIP。
- 在存放本说明的目录运行 `python -X utf8 -m unittest discover -s tests`。测试使用生成的模拟票据。
- 提交内容限通用说明、脚本、模拟测试和虚构示例。个人配置和每月报销资料保存在各自授权的位置。

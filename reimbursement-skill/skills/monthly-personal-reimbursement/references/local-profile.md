# 个人报销配置

每位使用者在自己的电脑上配置邮箱、台账、票据目录和报销主体。配置文件统一为 `$CODEX_HOME/profiles/monthly-personal-reimbursement.json`。未设置 `CODEX_HOME` 时，使用 `~/.codex`。

## 安装配置

在仓库中包含 `examples/` 的报销技能目录运行下方命令。若目标已存在，命令会保留现有配置。将样例值换成自己的实际值，并用 UTF-8 保存 JSON 文件。

**Windows PowerShell**

```powershell
$reimbursementCodexDir = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$reimbursementProfileDir = Join-Path $reimbursementCodexDir 'profiles'
$reimbursementProfile = Join-Path $reimbursementProfileDir 'monthly-personal-reimbursement.json'
New-Item -ItemType Directory -Path $reimbursementProfileDir -Force | Out-Null
if (-not (Test-Path -LiteralPath $reimbursementProfile)) {
    Copy-Item -LiteralPath '.\examples\reimbursement-profile.example.json' -Destination $reimbursementProfile
}
notepad.exe $reimbursementProfile
```

**macOS / Linux**

```sh
reimbursement_codex_dir="${CODEX_HOME:-$HOME/.codex}"
reimbursement_profile_dir="$reimbursement_codex_dir/profiles"
reimbursement_profile="$reimbursement_profile_dir/monthly-personal-reimbursement.json"
mkdir -p "$reimbursement_profile_dir"
if [ ! -e "$reimbursement_profile" ]; then
    cp examples/reimbursement-profile.example.json "$reimbursement_profile"
fi
printf '%s\n' "$reimbursement_profile"
```

打开命令输出的文件并修改。路径用绝对路径。Windows 路径可统一使用正斜杠，例如 `C:/Work/Reimbursements/receipts`。

## 字段

| 字段 | 填写规则 |
|---|---|
| `mailbox` | 报销发票通常收到的邮箱地址。需要查邮件时，确认当前连接或已登录账号确实能访问这个收件箱。 |
| `preferred_mail_client` | 可选。能访问该收件箱的工具或已登录客户端，例如“已连接邮箱”或你常用客户端的名称。 |
| `ledger_path` | 本人实际使用的报销 Excel 绝对路径。台账跨年或迁移后检查路径是否仍适用。 |
| `worksheet` | 对应工作簿内的工作表名称。 |
| `reimbursement_root` | 报销文件夹的上级目录，供查找当期目录时使用。 |
| `groups` | 报销主体列表。每项的 `name` 为台账及压缩包使用的分组名，`buyer_names` 为经核实属于该主体的发票购方全称列表。 |

只配置工作需要的字段。纯打包任务无需邮箱，有明确指定的工作簿或目录时直接使用指定位置。配置描述数据入口，邮件连接及文件权限按本轮实际授权处理。配置文件只保存在本人电脑，样例里使用虚构值。邮箱密码、访问令牌和真实报销材料应留在各自的授权存储位置。

## 每次使用

用户本轮给出的报销月份、分组、来源和目标目录优先。再从配置补足定位信息，并回读实际台账或票据。报销月份、开票月份和目录名称可以不同。若找不到当期目录，或候选目录与台账期间相冲突，先报告冲突并继续核对已取得的文件，由用户明确落盘位置后再写入。

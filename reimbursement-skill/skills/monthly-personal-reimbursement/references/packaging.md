# ZIP 打包说明

先从原票和通行明细完成内容核对，再在本轮可写的暂存目录生成 UTF-8 JSON。脚本根据清单校验重复票、金额合计、对应关系、PDF 文件和 ZIP 完整性，并原样打包 PDF。票面内容的核验应在生成清单前完成。

在技能目录内运行。也可以用脚本的绝对路径从其他目录运行。

```text
python -X utf8 scripts/pack_verified.py <清单.json> --source-root <已授权票据目录的绝对路径> --output-dir <暂存目录的绝对路径>
```

两处目录须已存在。清单里 `path` 相对于票据目录。一个 `groups` 元素对应一个 ZIP，`name` 是不带扩展名的包名，可用“报销月份-主体-金额”。`total` 和 `amount` 用小数字符串。各组填写 `invoices` 与 `trips`，没有独立行程单时 `trips` 用空数组。发票 `id` 使用核实的完整发票号。行程单 `invoice_ids` 可对应同组一张或多张发票。

```json
{
  "groups": [
    {
      "name": "示例月报销-主体-12.00元",
      "total": "12.00",
      "invoices": [
        {"id": "TEST-INVOICE-01", "amount": "12.00", "path": "示例发票.pdf"}
      ],
      "trips": [
        {
          "invoice_ids": ["TEST-INVOICE-01"],
          "path": "示例明细.zip",
          "member": "trans.pdf",
          "name": "示例行程单.pdf"
        }
      ]
    }
  ]
}
```

发票 `name` 可用来指定包内文件名，省略时沿用原名。行程单已是独立 PDF 时，直接给它的 `path`，省略 `member`。任一条目可给出已核实的 `sha256`。交付只需最终 ZIP。清单、日志和暂存副本留在本轮工作区，不随 ZIP 交付。

#!/usr/bin/env python3
"""
开票请求报文参数检查工具
对应逻辑来自"开具报文明细提取器.html"

用法：
  python3 check_invoice_params.py '<JSON报文>'
  python3 check_invoice_params.py --file /path/to/params.json
  python3 check_invoice_params.py --json '{"items":[...],"invoiceAmount":...}'
"""

import sys
import json
import argparse


def format_num(n):
    """保留两位小数，去掉末尾 .00"""
    s = f"{n:.2f}"
    return s.rstrip('0').rstrip('.') if '.' in s else s


def check(data):
    items = data.get("items", [])
    errors = []

    invoice_amount = 0.0
    total_tax = 0.0
    last_discount_type = None

    for i, item in enumerate(items):
        line = i + 1
        unit_price = float(item["unitPrice"]) if item.get("unitPrice") is not None else None
        num = float(item["num"]) if item.get("num") is not None else None
        detail_amount = float(item["detailAmount"]) if item.get("detailAmount") is not None else None
        tax_rate = float(item["taxRate"]) if item.get("taxRate") is not None else None
        tax_amount = float(item["taxAmount"]) if item.get("taxAmount") is not None else None
        discount_type = item.get("discountType")  # None / "" / "0" / "1" / "2"

        if detail_amount is not None:
            invoice_amount += detail_amount
        if tax_amount is not None:
            total_tax += tax_amount

        line_errors = []

        # 1. 金额误差：单价 × 数量 与 detailAmount 误差 > 0.01
        if unit_price is not None and num is not None and detail_amount is not None:
            calc_amount = unit_price * num
            diff = abs(calc_amount - detail_amount)
            if diff > 0.01:
                line_errors.append(
                    f"金额误差：{unit_price} × {num} = {format_num(calc_amount)}，"
                    f"detailAmount={format_num(detail_amount)}，误差={format_num(diff)}"
                )

        # 2. 税额误差：折扣行(discountType=1) 允许 0.01，其余允许 0.06
        if detail_amount is not None and tax_rate is not None and tax_amount is not None:
            calc_tax = detail_amount * tax_rate
            diff = abs(calc_tax - tax_amount)
            threshold = 0.01 if discount_type == "1" else 0.06
            if diff > threshold:
                line_errors.append(
                    f"税额误差：{format_num(detail_amount)} × {tax_rate} = {format_num(calc_tax)}，"
                    f"taxAmount={format_num(tax_amount)}，误差={format_num(diff)}（阈值{threshold}）"
                )

        # 3. discountType 合法性 + 折扣行顺序
        valid_types = (None, "", "0", "1", "2")
        if discount_type not in valid_types:
            line_errors.append(f"discountType值无效({discount_type})，只能为空、0、1、2")
        elif last_discount_type == "2" and discount_type != "1":
            line_errors.append("折扣行顺序错误：上一行为被折扣行(2)，当前行必须为折扣行(1)")
        elif discount_type == "1" and last_discount_type != "2":
            line_errors.append("折扣行顺序错误：当前行为折扣行(1)，上一行必须为被折扣行(2)")

        if line_errors:
            errors.append(f"第{line}行（{item.get('goodsName', '')}）：")
            for e in line_errors:
                errors.append(f"  ❌ {e}")

        last_discount_type = discount_type

    # 4. 总计一致性
    total_amount = invoice_amount + total_tax
    data_invoice_amount = float(data.get("invoiceAmount", invoice_amount))
    data_total_tax = float(data.get("totalTaxAmount", total_tax))
    data_total_amount = float(data.get("totalAmount", total_amount))

    total_errors = []
    diff = abs(invoice_amount - data_invoice_amount)
    if diff > 0.01:
        total_errors.append(
            f"合计金额不一致：明细累加={format_num(invoice_amount)}，"
            f"报文invoiceAmount={format_num(data_invoice_amount)}，差异={format_num(diff)}"
        )
    diff = abs(total_tax - data_total_tax)
    if diff > 0.01:
        total_errors.append(
            f"合计税额不一致：明细累加={format_num(total_tax)}，"
            f"报文totalTaxAmount={format_num(data_total_tax)}，差异={format_num(diff)}"
        )
    diff = abs(total_amount - data_total_amount)
    if diff > 0.01:
        total_errors.append(
            f"价税合计不一致：明细累加={format_num(total_amount)}，"
            f"报文totalAmount={format_num(data_total_amount)}，差异={format_num(diff)}"
        )

    # 输出
    if not errors and not total_errors:
        print("✅ 检查通过，未发现问题")
        return

    if total_errors:
        print("【总计字段问题】")
        for e in total_errors:
            print(f"  ❌ {e}")
        print()

    if errors:
        print("【明细行问题】")
        for e in errors:
            print(e)


def main():
    parser = argparse.ArgumentParser(description="开票请求报文参数检查")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file", help="JSON 文件路径")
    group.add_argument("--json", help="JSON 字符串")
    parser.add_argument("json_positional", nargs="?", help="JSON 字符串（位置参数）")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw = f.read()
    elif args.json:
        raw = args.json
    elif args.json_positional:
        raw = args.json_positional
    else:
        raw = sys.stdin.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败：{e}")
        sys.exit(1)

    check(data)


if __name__ == "__main__":
    main()

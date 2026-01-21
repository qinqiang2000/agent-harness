#!/usr/bin/env python3
"""Diagnostic tool for troubleshooting empty query results.

Usage:
    python diagnose.py --tenant "微众银行" --year 2025
    python diagnose.py --tenant-id 1439857266877535232
    python diagnose.py --order-no TRX202505091003274090

Example:
    python diagnose.py --tenant "微众" --year 2025
"""

import sys
import os
import asyncio
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any
from decimal import Decimal

# Load environment variables from .env file
from dotenv import load_dotenv
# Try to find .env in current working directory or parent directories
current_dir = Path.cwd()
env_file = current_dir / '.env'
if not env_file.exists():
    # Try parent directories (up to 4 levels)
    for i in range(4):
        current_dir = current_dir.parent
        env_file = current_dir / '.env'
        if env_file.exists():
            break
if env_file.exists():
    load_dotenv(env_file)

# Add scripts directory to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    import query_executor
    import result_formatter
    QueryExecutor = query_executor.QueryExecutor
    ResultFormatter = result_formatter.ResultFormatter
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保已安装依赖:")
    print("  source .venv/bin/activate && pip install -r requirements.txt")
    sys.exit(1)


class Diagnostics:
    """Diagnostic checks for EOP database queries."""

    def __init__(self):
        self.executor = QueryExecutor()
        self.formatter = ResultFormatter()

    async def close(self):
        """Close database connection."""
        await self.executor.close()

    async def check_tenant(self, tenant_name: str) -> Optional[Dict[str, Any]]:
        """Check if tenant exists and return basic info.

        Args:
            tenant_name: Tenant name to search (supports LIKE pattern)

        Returns:
            Tenant info dict or None if not found
        """
        sql = f"""
        SELECT fid, fname, fenable, fcontact_name, fcontact_phone
        FROM t_ocm_tenant
        WHERE fname LIKE '%{tenant_name}%'
        LIMIT 10
        """
        results = await self.executor.execute(sql)
        return results

    async def check_orders(self, tenant_id: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Check orders for a tenant.

        Args:
            tenant_id: Tenant ID
            year: Optional year filter

        Returns:
            List of order info dicts
        """
        time_filter = ""
        if year:
            time_filter = f"AND h.fcreatetime >= '{year}-01-01' AND h.fcreatetime < '{year + 1}-01-01'"

        sql = f"""
        SELECT
            h.fbillno,
            h.fcreatetime,
            h.fbusiness_type,
            h.fbiz_type,
            h.ftotal_amount,
            h.fproduct_num
        FROM t_ocm_order_header h
        WHERE h.ftenant = '{tenant_id}'
        {time_filter}
        ORDER BY h.fcreatetime DESC
        LIMIT 20
        """
        results = await self.executor.execute(sql)
        return results

    async def check_order_lines(self, order_ids: List[str]) -> Dict[str, int]:
        """Check if orders have product lines.

        Args:
            order_ids: List of order IDs (fid from t_ocm_order_header)

        Returns:
            Dict mapping order_id to line count
        """
        if not order_ids:
            return {}

        ids_str = ','.join(f"'{oid}'" for oid in order_ids)
        sql = f"""
        SELECT fentryid, COUNT(*) as line_count
        FROM t_ocm_order_lines
        WHERE fentryid IN ({ids_str})
        GROUP BY fentryid
        """
        results = await self.executor.execute(sql)
        return {str(row['fentryid']): row['line_count'] for row in results}

    async def check_settle_records(self, order_nos: List[str]) -> List[Dict[str, Any]]:
        """Check settlement records for orders.

        Args:
            order_nos: List of order numbers (fbillno)

        Returns:
            List of settlement records
        """
        if not order_nos:
            return []

        # Try to match by partial order number
        like_conditions = " OR ".join(f"fkbc_settle_billno LIKE '%{no[-10:]}%'" for no in order_nos)
        sql = f"""
        SELECT
            fkbc_settle_billno,
            fpost_date,
            fsale_product_name,
            fversion_no,
            fdelivery_status,
            famount
        FROM t_ocm_kbc_order_settle
        WHERE {like_conditions}
        LIMIT 50
        """
        results = await self.executor.execute(sql)
        return results

    async def diagnose_tenant_orders(self, tenant_name: str, year: Optional[int] = None):
        """Full diagnostic for tenant orders.

        Args:
            tenant_name: Tenant name to search
            year: Optional year to check
        """
        print(f"## 诊断报告: {tenant_name}" + (f" ({year}年)" if year else ""))
        print()

        # Step 1: Check tenant
        print("### 1. 检查租户是否存在")
        tenants = await self.check_tenant(tenant_name)
        if not tenants:
            print(f"❌ 未找到包含 '{tenant_name}' 的租户\n")
            print("💡 建议:")
            print(f"  - 尝试使用更短的关键词搜索")
            print(f"  - 检查租户名称拼写\n")
            return

        print(f"✅ 找到 {len(tenants)} 个匹配的租户:\n")
        for t in tenants:
            status = "可用" if t['fenable'] == 1 else "禁用"
            print(f"  - ID: {t['fid']}")
            print(f"    名称: {t['fname']}")
            print(f"    状态: {status}")
            if t['fcontact_name']:
                print(f"    联系人: {t['fcontact_name']} ({t['fcontact_phone']})")
            print()

        # Use first tenant for further checks
        tenant_id = str(tenants[0]['fid'])
        tenant_full_name = tenants[0]['fname']

        # Step 2: Check orders
        print(f"### 2. 检查订单记录")
        orders = await self.check_orders(tenant_id, year)
        if not orders:
            print(f"❌ 租户 '{tenant_full_name}' 在{year}年没有订单\n")
            print("💡 建议:")
            print(f"  - 检查时间范围是否正确")
            print(f"  - 尝试查询其他年份\n")

            # Check if tenant has any orders
            all_orders = await self.check_orders(tenant_id)
            if all_orders:
                print(f"ℹ️  该租户在其他时间段有 {len(all_orders)} 条订单")
                print(f"   最早: {all_orders[-1]['fcreatetime']}")
                print(f"   最近: {all_orders[0]['fcreatetime']}\n")
            return

        print(f"✅ 找到 {len(orders)} 条订单:\n")

        # Calculate statistics
        standard_orders = [o for o in orders if o['fbiz_type'] == 'Standard']
        total_amount = sum(float(o['ftotal_amount'] or 0) for o in orders)
        paid_amount = sum(float(o['ftotal_amount'] or 0) for o in standard_orders)

        print(self.formatter.to_markdown_table(orders))
        print()
        print("**统计信息**:")
        print(f"  - 订单总数: {len(orders)}")
        print(f"  - 付费订单: {len(standard_orders)}")
        print(f"  - 订单总额: ¥{total_amount:,.2f}")
        print(f"  - 付费金额: ¥{paid_amount:,.2f}")
        print()

        # Step 3: Check product lines
        print(f"### 3. 检查产品明细")
        order_ids = [str(o['fbillno']) for o in orders]  # Actually using fid would be better
        # Get order fids by querying again (we only have fbillno in results)
        fid_sql = f"""
        SELECT fid FROM t_ocm_order_header
        WHERE fbillno IN ({','.join(f"'{oid}'" for oid in order_ids)})
        """
        order_fids_result = await self.executor.execute(fid_sql)
        order_fids = [str(r['fid']) for r in order_fids_result]

        line_counts = await self.check_order_lines(order_fids)

        if not line_counts:
            print(f"⚠️  这些订单在产品明细表（t_ocm_order_lines）中没有数据\n")
            print("💡 说明:")
            print(f"  - 产品明细数据可能尚未同步")
            print(f"  - 建议使用 t_ocm_order_header.ftotal_amount 获取订单金额")
            print(f"  - 可以尝试从结算表（t_ocm_kbc_order_settle）查询产品信息\n")
        else:
            print(f"✅ 部分订单有产品明细:\n")
            for order_id, count in line_counts.items():
                print(f"  - 订单 {order_id}: {count} 个产品")
            print()

        # Step 4: Check settlement records
        print(f"### 4. 检查结算记录")
        settle_records = await self.check_settle_records(order_ids)

        if not settle_records:
            print(f"⚠️  未找到关联的结算记录\n")
            print("💡 说明:")
            print(f"  - 结算数据可能通过其他方式关联")
            print(f"  - 订单金额可直接从 t_ocm_order_header.ftotal_amount 获取\n")
        else:
            print(f"✅ 找到 {len(settle_records)} 条结算记录:\n")
            print(self.formatter.to_markdown_table(settle_records))
            print()

        # Summary
        print("### 诊断总结\n")
        print(f"✅ 租户存在: {tenant_full_name}")
        print(f"✅ {year}年订单: {len(orders)} 条")
        if line_counts:
            print(f"✅ 产品明细: 部分订单有明细")
        else:
            print(f"⚠️  产品明细: 无数据（正常情况）")
        if settle_records:
            print(f"✅ 结算记录: {len(settle_records)} 条")
        else:
            print(f"⚠️  结算记录: 未找到关联")
        print()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="诊断 EOP 数据库查询问题",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--tenant', help='租户名称（支持模糊匹配）')
    parser.add_argument('--tenant-id', help='租户ID')
    parser.add_argument('--year', type=int, help='年份')
    parser.add_argument('--order-no', help='订单号')

    args = parser.parse_args()

    if not any([args.tenant, args.tenant_id, args.order_no]):
        parser.print_help()
        sys.exit(1)

    diag = Diagnostics()

    try:
        if args.tenant:
            await diag.diagnose_tenant_orders(args.tenant, args.year)
        elif args.tenant_id:
            # TODO: Implement diagnose by tenant_id
            print("暂未实现 --tenant-id 参数")
        elif args.order_no:
            # TODO: Implement diagnose by order_no
            print("暂未实现 --order-no 参数")
    finally:
        await diag.close()


if __name__ == '__main__':
    asyncio.run(main())

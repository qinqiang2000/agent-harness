"""测试会话超时机制

这个脚本演示 YunzhijiaHandler 的会话超时功能：
1. 创建新会话
2. 更新会话活动时间
3. 检查超时
4. 清理过期会话
"""

import time
from api.handlers.yunzhijia_handler import YunzhijiaHandler
from api.services.agent_service import AgentService
from api.services.session_service import SessionService


class MockAgentService:
    """模拟 AgentService"""
    pass


class MockSessionService:
    """模拟 SessionService"""
    pass


def test_session_timeout():
    """测试会话超时机制"""

    # 创建 handler（使用默认 30 分钟超时）
    handler = YunzhijiaHandler(MockAgentService(), MockSessionService())

    # 临时设置较短的超时时间用于测试（5 秒）
    handler.SESSION_TIMEOUT_SECONDS = 5

    print(f"✓ 创建 handler，超时时间: {handler.SESSION_TIMEOUT_SECONDS} 秒\n")

    # 场景 1: 创建会话
    print("场景 1: 创建新会话")
    yzj_session_1 = "yzj_session_001"
    agent_session_1 = "agent_session_001"
    handler._update_session_activity(yzj_session_1, agent_session_1)
    print(f"  创建会话: {yzj_session_1} -> {agent_session_1}")
    print(f"  当前会话数: {len(handler.session_map)}\n")

    # 场景 2: 会话未超时
    print("场景 2: 立即检查会话（未超时）")
    result = handler._check_session_timeout(yzj_session_1)
    print(f"  检查结果: {result}")
    print(f"  预期: {agent_session_1}")
    print(f"  ✓ 通过\n" if result == agent_session_1 else "  ✗ 失败\n")

    # 场景 3: 创建第二个会话
    print("场景 3: 创建第二个会话")
    yzj_session_2 = "yzj_session_002"
    agent_session_2 = "agent_session_002"
    handler._update_session_activity(yzj_session_2, agent_session_2)
    print(f"  创建会话: {yzj_session_2} -> {agent_session_2}")
    print(f"  当前会话数: {len(handler.session_map)}\n")

    # 场景 4: 等待第一个会话超时
    print(f"场景 4: 等待 {handler.SESSION_TIMEOUT_SECONDS + 1} 秒后检查第一个会话（应超时）")
    time.sleep(handler.SESSION_TIMEOUT_SECONDS + 1)
    result = handler._check_session_timeout(yzj_session_1)
    print(f"  检查结果: {result}")
    print(f"  预期: None（已超时）")
    print(f"  ✓ 通过\n" if result is None else f"  ✗ 失败（返回 {result}）\n")

    # 场景 5: 第二个会话应该也超时了
    print("场景 5: 检查第二个会话（也应超时）")
    result = handler._check_session_timeout(yzj_session_2)
    print(f"  检查结果: {result}")
    print(f"  预期: None（已超时）")
    print(f"  ✓ 通过\n" if result is None else f"  ✗ 失败（返回 {result}）\n")

    # 场景 6: 创建新会话并更新活动时间
    print("场景 6: 创建会话并持续更新活动时间")
    yzj_session_3 = "yzj_session_003"
    agent_session_3 = "agent_session_003"
    handler._update_session_activity(yzj_session_3, agent_session_3)
    print(f"  创建会话: {yzj_session_3}")

    for i in range(3):
        time.sleep(2)
        handler._update_session_activity(yzj_session_3, agent_session_3)
        print(f"  更新活动时间 #{i+1}")

    result = handler._check_session_timeout(yzj_session_3)
    print(f"  检查结果: {result}")
    print(f"  预期: {agent_session_3}（持续活动，未超时）")
    print(f"  ✓ 通过\n" if result == agent_session_3 else f"  ✗ 失败\n")

    # 场景 7: 测试批量清理
    print("场景 7: 测试批量清理过期会话")
    # 创建多个会话
    for i in range(5):
        handler._update_session_activity(f"yzj_{i}", f"agent_{i}")
    print(f"  创建了 5 个会话，当前总数: {len(handler.session_map)}")

    # 等待超时
    time.sleep(handler.SESSION_TIMEOUT_SECONDS + 1)

    # 清理过期会话
    handler._cleanup_expired_sessions()
    print(f"  清理后会话数: {len(handler.session_map)}")
    print(f"  预期: 0")
    print(f"  ✓ 通过\n" if len(handler.session_map) == 0 else f"  ✗ 失败\n")

    # 场景 8: 测试 get_session_stats
    print("场景 8: 测试会话统计功能")
    handler._update_session_activity("yzj_test_1", "agent_test_1")
    time.sleep(1)
    handler._update_session_activity("yzj_test_2", "agent_test_2")

    stats = handler.get_session_stats()
    print(f"  统计信息:")
    print(f"    总会话数: {stats['total_sessions']}")
    print(f"    超时阈值: {stats['session_timeout_seconds']} 秒")
    for session in stats['sessions']:
        print(f"    - {session['yzj_session_id']}: 不活跃 {session['inactive_seconds']}s, "
              f"{session['will_expire_in']}s 后过期")
    print(f"  ✓ 通过\n")

    print("=" * 60)
    print("所有测试完成！")


if __name__ == "__main__":
    test_session_timeout()

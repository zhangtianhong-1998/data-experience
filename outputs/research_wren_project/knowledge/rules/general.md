# 设备订货与利润实验规则

- `total_device_orders = SUM(device_order_amount)` 与 `total_device_profit = SUM(device_profit_amount)` 只复现已观察到的 BI 计算，不代表企业级权威口径。
- `year_month` 当前是字符串；在值格式和时区未验证前，不进行自动日期截断或财年转换。
- SQL 中 `c7 = ?` 与 `c0 = ?` 的占位条件缺少参数名称，Agent 必须显式披露未应用这些原看板过滤条件。
- 不得臆测金额单位、币种、含税/未税、利润类型或组织范围。
- 当问题要求“官方”“财务确认”或跨看板比较时，应返回需要补证，而不是直接使用本实验 cube。

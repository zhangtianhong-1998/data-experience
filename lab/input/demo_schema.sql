-- 只创建表结构和字段备注线索，不插入业务数据。
CREATE TABLE device_order_profit (
  c0 TEXT NOT NULL,
  c2 TEXT NOT NULL,
  c7 TEXT NOT NULL,
  c27 NUMERIC,
  c28 NUMERIC
);

CREATE TABLE product_master (
  product_code TEXT PRIMARY KEY,
  product_l1 TEXT NOT NULL,
  product_name TEXT
);

CREATE VIEW device_order_profit_by_product AS
SELECT
  c7 AS product_l1,
  c2 AS year_month,
  SUM(c27) AS device_order_amount,
  SUM(c28) AS device_profit_amount
FROM device_order_profit
GROUP BY c7, c2;

DROP DATABASE IF EXISTS enterprise_demo;
SET GLOBAL local_infile = 1;
CREATE DATABASE enterprise_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE enterprise_demo;

CREATE TABLE device_orders (
  order_id VARCHAR(20) PRIMARY KEY COMMENT '设备订货单唯一编号',
  order_date DATE NOT NULL COMMENT '订货日期',
  `year_month` INT NOT NULL COMMENT '自然年月，YYYYMM',
  org_code VARCHAR(20) NOT NULL COMMENT '数据权限组织编码，查询必须显式限定',
  product_code VARCHAR(20) NOT NULL COMMENT '产品编码',
  product_l1 VARCHAR(50) NOT NULL COMMENT '一级产品分类',
  country VARCHAR(50) COMMENT '客户国家',
  status VARCHAR(20) NOT NULL COMMENT 'confirmed 才计入设备订货指标',
  order_amount DECIMAL(18,2) COMMENT '设备订货金额，CNY',
  profit_amount DECIMAL(18,2) COMMENT '设备毛利金额，CNY'
) COMMENT='设备订货事实表；每行一张订单，取消单不得计入指标';

LOAD DATA LOCAL INFILE '/tmp/device_orders.csv'
INTO TABLE device_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, order_date, `year_month`, org_code, product_code, product_l1,
 order_amount, profit_amount, country, status);
DELETE FROM device_orders WHERE order_id = '';

CREATE VIEW device_orders_by_product AS
SELECT product_l1,
       SUM(order_amount) AS device_order_amount,
       SUM(profit_amount) AS device_profit_amount
FROM device_orders
WHERE status = 'confirmed'
GROUP BY product_l1;

CREATE TABLE sales_orders (
  sale_id VARCHAR(20) PRIMARY KEY COMMENT '销售单编号',
  org_code VARCHAR(20) NOT NULL,
  product_l1 VARCHAR(50) NOT NULL,
  sale_amount DECIMAL(18,2) COMMENT '销售收入，不是设备订货金额'
) COMMENT='故意放入的近义干扰表，不能回答设备订货问题';

INSERT INTO sales_orders VALUES
('S001', 'ORG_1001', 'Compute', 99999),
('S002', 'ORG_1001', 'Network', 88888),
('S003', 'ORG_2001', 'IoT', 77777);

CREATE USER IF NOT EXISTS 'demo_reader'@'%' IDENTIFIED BY 'reader_password';
GRANT SELECT, SHOW VIEW ON enterprise_demo.* TO 'demo_reader'@'%';
FLUSH PRIVILEGES;

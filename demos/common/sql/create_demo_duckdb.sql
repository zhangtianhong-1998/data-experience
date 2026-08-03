CREATE OR REPLACE TABLE device_orders AS
SELECT * FROM read_csv_auto('data/device_orders.csv', header = true);

CREATE OR REPLACE TABLE product_master AS
SELECT * FROM read_csv_auto('data/product_master.csv', header = true);

CREATE OR REPLACE TABLE sales_orders AS
SELECT * FROM read_csv_auto('data/sales_orders.csv', header = true);

CREATE OR REPLACE VIEW deprecated_device_orders AS
SELECT * FROM device_orders WHERE 1 = 0;


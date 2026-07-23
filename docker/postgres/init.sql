CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(200),
    age INT
);

INSERT INTO users (name, email, age) VALUES
    ('admin', 'admin@example.com', 30),
    ('alice', 'alice@example.com', 25),
    ('bob', 'bob@example.com', 28),
    ('charlie', 'charlie@example.com', 35),
    ('dave', 'dave@example.com', 22);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    price NUMERIC(10,2)
);

INSERT INTO products (name, price) VALUES
    ('Laptop', 999.99),
    ('Mouse', 25.50),
    ('Keyboard', 75.00),
    ('Monitor', 299.99),
    ('Headset', 89.99);

CREATE TABLE IF NOT EXISTS profiles (
    uid INT PRIMARY KEY,
    bio TEXT,
    join_date DATE
);

INSERT INTO profiles (uid, bio, join_date) VALUES
    (1, 'System administrator', '2024-01-15'),
    (2, 'Software engineer', '2024-03-20'),
    (3, 'DevOps engineer', '2024-06-10'),
    (4, 'Data scientist', '2024-09-05'),
    (5, 'Junior developer', '2025-02-01');

CREATE TABLE IF NOT EXISTS orders (
    oid SERIAL PRIMARY KEY,
    uid INT,
    total NUMERIC(10,2)
);

INSERT INTO orders (uid, total) VALUES
    (1, 1299.99),
    (2, 75.00),
    (3, 389.98),
    (4, 25.50),
    (5, 999.99);

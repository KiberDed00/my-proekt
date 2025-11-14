CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Очистка таблицы и вставка тестовых данных
TRUNCATE TABLE products RESTART IDENTITY CASCADE;

INSERT INTO products (name, price, category, description) VALUES
('iPhone 15 Pro', 99999.99, 'Смартфоны', 'Флагманский смартфон Apple с камерой 48 МП'),
('MacBook Air M2', 124999.99, 'Ноутбуки', 'Ультратонкий ноутбук с чипом Apple M2'),
('Samsung Galaxy S24', 79999.99, 'Смартфоны', 'Android-смартфон с AI функциями'),
('iPad Air', 65999.99, 'Планшеты', 'Мощный планшет для работы и творчества'),
('AirPods Pro', 24999.99, 'Аксессуары', 'Наушники с шумоподавлением'),
('Gaming PC', 189999.99, 'Компьютеры', 'Игровой компьютер с RTX 4080');
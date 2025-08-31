CREATE DATABASE IF NOT EXISTS book_db;
USE book_db;

CREATE TABLE IF NOT EXISTS books (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username VARCHAR(100),
    isbn VARCHAR(32),
    title VARCHAR(255),
    authors TEXT,
    description LONGTEXT,
    cover TEXT,
    due_date DATE,
    reminded BOOLEAN DEFAULT FALSE,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_isbn (user_id,isbn)
);

CREATE TABLE IF NOT EXISTS rueckgabe_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    moderator_id BIGINT,
    user_id BIGINT,
    isbn VARCHAR(32),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- For a fresh, isolated LAB cluster only; execute ONCE as the yugabyte admin.
-- Do not put plaintext passwords in this file or commit a .env containing secrets.
-- The operator sets an interactive password with: \password banking_app
CREATE ROLE banking_app LOGIN;
CREATE DATABASE banking OWNER banking_app;
CREATE DATABASE banking_test OWNER banking_app;

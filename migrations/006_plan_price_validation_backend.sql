BEGIN;

-- La validación de precio positivo y precisión se realiza en los schemas del backend.
-- Se mantienen NUMERIC(10,2), NOT NULL, nombre único y duración positiva.
ALTER TABLE plans DROP CONSTRAINT IF EXISTS plans_price_check;

COMMIT;

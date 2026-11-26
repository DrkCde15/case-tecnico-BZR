BEGIN;

ALTER TABLE precatorio
    ALTER COLUMN numero_processo TYPE VARCHAR(25);

ALTER TABLE precatorio
    ADD CONSTRAINT precatorio_numero_processo_cnj
    CHECK (
        numero_processo ~ '^[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}$'
    ) NOT VALID;

CREATE TABLE importacao (
    id                BIGSERIAL PRIMARY KEY,
    arquivo           TEXT        NOT NULL,
    hash_arquivo      CHAR(64)    NOT NULL UNIQUE,
    status            TEXT        NOT NULL DEFAULT 'recebido'
                      CHECK (status IN ('recebido', 'processado', 'falhou')),
    recebido_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    processado_em     TIMESTAMPTZ,
    total_registros   INTEGER     NOT NULL DEFAULT 0 CHECK (total_registros >= 0),
    total_importados  INTEGER     NOT NULL DEFAULT 0 CHECK (total_importados >= 0),
    total_rejeitados  INTEGER     NOT NULL DEFAULT 0 CHECK (total_rejeitados >= 0),
    mensagem          TEXT
);

CREATE TABLE pagamento_staging (
    id             BIGSERIAL PRIMARY KEY,
    importacao_id  BIGINT      NOT NULL
                   REFERENCES importacao (id) ON DELETE CASCADE,
    evento_id      TEXT,
    processo       TEXT,
    valor          TEXT,
    data_pagamento TEXT,
    tipo           TEXT,
    atualizado_em  TEXT,
    precatorio_id  BIGINT      REFERENCES precatorio (id),
    payload        JSONB       NOT NULL,
    status         TEXT        NOT NULL DEFAULT 'pendente'
                   CHECK (status IN ('pendente', 'importado', 'rejeitado')),
    motivo         TEXT,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (importacao_id, evento_id)
);

CREATE INDEX idx_pagamento_staging_pendente
    ON pagamento_staging (importacao_id, status);

DELETE FROM pagamento a
USING pagamento b
WHERE a.evento_id = b.evento_id
  AND a.id > b.id
  AND a.precatorio_id = b.precatorio_id
  AND a.tipo = b.tipo
  AND a.valor = b.valor
  AND a.pago_em = b.pago_em;

ALTER TABLE pagamento
    ADD CONSTRAINT uq_pagamento_evento UNIQUE (evento_id),
    ADD COLUMN atualizado_em TIMESTAMPTZ,
    ADD COLUMN importacao_id BIGINT REFERENCES importacao (id);

ALTER TABLE pagamento
    DROP CONSTRAINT IF EXISTS pagamento_tipo_check,
    ADD CONSTRAINT pagamento_tipo_check
        CHECK (tipo IN ('pagamento', 'estorno'));

ALTER TABLE pagamento
    DROP CONSTRAINT IF EXISTS pagamento_valor_check,
    ADD CONSTRAINT pagamento_valor_check
        CHECK (
            (tipo = 'pagamento' AND valor > 0)
            OR (tipo = 'estorno' AND valor < 0)
        );

CREATE INDEX idx_pagamento_precatorio_pago_em
    ON pagamento (precatorio_id, pago_em);

CREATE INDEX idx_pagamento_importacao
    ON pagamento (importacao_id);

COMMIT;

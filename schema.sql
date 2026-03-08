-- Ejecutar en SQL Editor de Supabase
CREATE TABLE citas (
  id         BIGSERIAL PRIMARY KEY,
  phone      TEXT NOT NULL,
  event_id   TEXT NOT NULL,
  fecha_cita TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE citas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "solo autenticados" ON citas FOR ALL USING (auth.uid() IS NOT NULL);

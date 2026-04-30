import psycopg2

configs = [
    {"sslmode": "disable"},
    {"sslmode": "allow"},
    {"sslmode": "prefer"},
    {"sslmode": "require"},
]

for cfg in configs:
    try:
        print(f"Probando sslmode={cfg['sslmode']}...", end=" ")
        conn = psycopg2.connect(
            host="edb-analytic-consumer-prod.carpdwnmaayt.us-east-2.redshift.amazonaws.com",
            port=5439,
            dbname="mq_dia_gmdf",
            user="gmdf_ref_alco_qc_rpt",
            password="Alcogardens#7612",
            connect_timeout=10,
            **cfg
        )
        print("CONECTADO!")
        conn.close()
        break
    except Exception as e:
        print(f"Fallo: {e}")

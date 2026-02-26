import sqlite3
from pathlib import Path


def main(db_path: str = "jobpulse.db", limit: int = 10) -> None:
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_file}")
        return

    with sqlite3.connect(str(db_file)) as conn:
        cur = conn.cursor()
        cur.execute("select count(*) from job_offers")
        total = cur.fetchone()[0]
        print(f"rows: {total}")

        cur.execute(
            """
            select source, external_id, title, company, city,
                   salary_min_pln, salary_max_pln, offer_url
            from job_offers
            order by id desc
            limit ?
            """,
            (limit,),
        )
        for row in cur.fetchall():
            print(row)


if __name__ == "__main__":
    main()

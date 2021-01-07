# using new version of ratools where DB is an object

from ratools.db import DB

db = DB.from_config()

df = db.read_sql('select * from analytics_sandbox.tableau_users limit 10')

print(df)
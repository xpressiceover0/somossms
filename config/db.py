from sqlalchemy import create_engine, MetaData

engine=create_engine("mysql://root:Xpressiceover1@db/somosdb")
meta=MetaData()
conn=engine.connect()

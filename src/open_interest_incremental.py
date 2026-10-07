import pandas as pd
A=pd.read_csv("results/open_interest_events.csv")
B=A[(A["anchor"]==True)]
T=B[(B["target"]==True)]
rows=[]
for label,g in [("anchor",B),("target_anchor",T)]:
  for state,h in g.groupby("oi_state_4h"):
    for n in [2,3,6,12]:
      x=h[f"net_{n}h"].dropna(); rows.append({"set":label,"state":state,"n":len(x),"avg_net":x.mean(),"median_net":x.median(),"win_rate":(x>0).mean()})
for label,g in [("anchor",B),("target_anchor",T)]:
  for state,h in g.groupby("oi_state_12h"):
    for n in [2,3,6,12]:
      x=h[f"net_{n}h"].dropna(); rows.append({"set":label,"state":"12h_"+state,"n":len(x),"avg_net":x.mean(),"median_net":x.median(),"win_rate":(x>0).mean()})
pd.DataFrame(rows).to_csv("results/open_interest_incremental.csv",index=False)
print(pd.DataFrame(rows).to_string(index=False))

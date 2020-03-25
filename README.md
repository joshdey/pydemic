api description below

## information in a population model

```
"populationServed": 8600000, 
"country": "Switzerland", 
"hospitalBeds": 30799, 
"ICUBeds": 1400, 
"suspectedCasesToday": 1148, 
"importsPerDay": 4.0, 
"cases": "Switzerland"

"0-9": 4994996,
"10-19": 5733447,
"20-29": 6103437,
"30-39": 6998434,
"40-49": 9022004,
"50-59": 9567192,
"60-69": 7484860,
"70-79": 6028907,
"80+": 4528548
```

These data should be passed in a dictionary structured as follows:

```python
population = {
  # total demographic information and labels
  "country": "Switzerland",
  "cases": "Switzerland",
  "populationServed": 8600000,
  # reported medical facilities
  "hospitalBeds": 30799,
  "ICUBeds": 1400,
  # estimated infectivity model parameters
  "suspectedCasesToday": 1148,
  "importedPerDay": 4.0,
  # granular population statistics
  "populationsByDecade": [
    4994996,
    5733447,
    6103437,
    6998434,
    9022004,
    9567192,
    7484860,
    6028907,
    4528548
  ]
}
```

## containment data 

*this will change in the near future to enable finer granularity in time*

```python
containemnt = {
  "factors": [ 
    1.0, 
    0.9, 
    0.8, 
    0.8, 
    0.8, 
    0.8, 
    0.8, 
    0.8, 
    0.8, 
    0.8
  ]
}
```





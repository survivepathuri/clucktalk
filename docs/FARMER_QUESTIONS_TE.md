# రైతు ప్రశ్నల పత్రం (Telugu question sheet)

English summary: this file is the Telugu question list used for the farmer conversation.
It lists the questions in order (sheds, birds placed, placement date, deaths so far, feed stock), with an example answer and a unit for each.
It is supporting material, not part of the running product, and the Telugu wording is a first draft.
The rest of the page is in Telugu, with English column labels.

Use this at the farm with `deploy/cloud/make-farm.ps1`. Ask each question in order, one shed at a time, and type the
answer. The Telugu wording is a plain first draft: have a Telugu speaker read it before it is used with the farmer.

**ఇవి తప్ప ఇంకేమీ అడగొద్దు: పేరు, ఫోన్, ఆధార్, చిరునామా**
(Do not ask for anything else: name, phone, Aadhaar, address.)

| # | ప్రశ్న (question) | ఉదాహరణ జవాబు | ప్రమాణం (unit) | Script prompt |
|---|---|---|---|---|
| 1 | మీ దగ్గర ఎన్ని షెడ్లు ఉన్నాయి? | 2 | షెడ్లు (1 నుండి 6) | How many sheds |
| 2 | షెడ్ 1 లో ఎన్ని కోళ్లు వేశారు? | 3000 | కోళ్లు (1 నుండి 1,00,000) | birds placed |
| 3 | ఆ కోళ్లను ఏ తేదీన వేశారు? | 2026-10-01 | తేదీ (సంవత్సరం-నెల-రోజు) | placement date |
| 4 | ఇప్పటి వరకు ఎన్ని కోళ్లు చనిపోయాయి? | 25 | కోళ్లు (లేకపోతే 0) | birds that died so far |
| 5 | షెడ్ 1 లో ఇప్పుడు ఎంత దాణా నిల్వ ఉంది? | 500 | కిలోలు (తెలియకపోతే 0) | feed stock in kg |

ప్రశ్నలు 2 నుండి 5 వరకు ప్రతి షెడ్‌కు వేర్వేరుగా అడగండి (షెడ్ 2, షెడ్ 3 …).

## గమనికలు

- తేదీ తెలియకపోతే, "ఎన్ని రోజుల క్రితం వేశారు?" అని అడిగి, ఈరోజు నుండి వెనక్కి లెక్కించండి.
- సంఖ్య సరిగ్గా తెలియకపోతే అంచనా అని చెప్పి, రైతుతో ఒకసారి మళ్ళీ చదివి నిర్ధారించుకోండి.
- స్క్రిప్ట్ చివర్లో చూపే సారాంశాన్ని రైతుకు చదివి వినిపించి, "సరిగ్గా ఉందా?" అని అడగండి. సరిగ్గా ఉంటేనే "yes" అని టైప్ చేయండి.
- దాణా ధర, కోడి ధర, సరఫరాదారు రోజులు ఈ పత్రంలో లేవు: అవి నమూనా (placeholder) విలువలు, రైతు సొంత సంఖ్యలు కావు.

# get_farm_status and plan_feed: evidence (2026-09-27)

Real runs of `@modelcontextprotocol/inspector@2.8.0` CLI (`mcp-inspector --cli`) against `python tasks.py serve`
(demo mode: the seeded **fictional** farm, generated as of today in IST). JSON is unedited except `daily` arrays,
shortened where marked. Exit codes in brackets.

Sections 6-7 (error results): the Inspector prints the result and a JSON `tool_is_error`, then crashes on Windows
(libuv assertion, exit 0xC0000409). Reproduced 3/3 and also for an unknown tool, so it is the Inspector's error
exit path, not the server (FRICTION_LOG FL-005). Error results carry no `structuredContent` (FL-004).

## 1. `tools/list --strict`
```
get_farm_status | params: ['house'] | outputSchema: True
plan_feed | params: ['horizon_days', 'house'] | outputSchema: True
get_help | params: [] | outputSchema: True
stderr: (empty)
[exit 0]
```
## 2. `tools/call get_farm_status` (no arguments)
```json
{
  "content": [
    {
      "type": "text",
      "text": "Here's your farm today. House 2 needs attention now. 26 birds died today, against about 4 a day this past week. House 1 is doing well. House 3 is doing well. Please check the birds today and call your vet if deaths continue."
    }
  ],
  "structuredContent": {
    "text_en": "Here's your farm today. House 2 needs attention now. 26 birds died today, against about 4 a day this past week. House 1 is doing well. House 3 is doing well. Please check the birds today and call your vet if deaths continue.",
    "text_te": "ఈరోజు మీ ఫారం స్థితి. షెడ్ 2 కి వెంటనే శ్రద్ధ అవసరం. ఈరోజు 26 కోళ్లు చనిపోయాయి; గత వారం రోజుకు సుమారు 4. షెడ్ 1 బాగుంది. షెడ్ 3 బాగుంది. దయచేసి ఈరోజే కోళ్లను పరిశీలించండి, మరణాలు కొనసాగితే మీ పశువైద్యుడిని సంప్రదించండి.",
    "demo_data": true,
    "as_of": "2026-09-27",
    "level": "alert",
    "houses": [
      {
        "house_id": "house-2",
        "number": 2,
        "label_en": "House 2",
        "label_te": "షెడ్ 2",
        "kind": "broiler",
        "breed": "Ross 308",
        "level": "alert",
        "summary_en": "House 2 needs attention now. Day 23, 3,883 birds, average weight 941 g against the Ross 308 target of 1,012 g.",
        "summary_te": "షెడ్ 2 కి వెంటనే శ్రద్ధ అవసరం. 23వ రోజు, 3,883 కోళ్లు, సగటు బరువు 941 గ్రా. (Ross 308 లక్ష్యం 1,012 గ్రా.).",
        "latest_record_day": "2026-09-27",
        "age_days": 23,
        "birds_placed": 4000,
        "live_birds": 3883,
        "deaths_latest": 26,
        "deaths_7d": 50,
        "cum_mortality_pct": 2.9,
        "feed_latest_kg": 364,
        "feed_per_bird_g": 93,
        "avg_weight_g": 941,
        "target_weight_g": 1012,
        "farm_fcr": 1.23,
        "target_fcr": 1.14,
        "hen_day_pct": null,
        "hen_day_pct_7d_avg": null,
        "feed_days_covered": 2,
        "feed_days_covered_is_minimum": false,
        "findings": [
          {
            "code": "mortality_spike",
            "level": "alert",
            "text_en": "26 birds died today, against about 4 a day this past week.",
            "text_te": "ఈరోజు 26 కోళ్లు చనిపోయాయి; గత వారం రోజుకు సుమారు 4.",
            "values": {
              "deaths": 26,
              "baseline_per_day": 4
            }
          },
          {
            "code": "feed_intake_drop",
            "level": "watch",
            "text_en": "Birds ate 18% less than expected: 93 g per bird against 114 g.",
            "text_te": "కోళ్లు అంచనా కంటే 18% తక్కువ తిన్నాయి: ఒక్కో కోడికి 93 గ్రా., అంచనా 114 గ్రా.",
            "values": {
              "per_bird_g": 93,
              "expected_per_bird_g": 114,
              "drop_pct": 18
            }
          },
          {
            "code": "feed_stock_low",
            "level": "watch",
            "text_en": "Feed stock lasts about 2 days.",
            "text_te": "దాణా నిల్వ సుమారు 2 రోజులు సరిపోతుంది.",
            "values": {
              "days_covered": 2
            }
          }
        ]
      },
      {
        "house_id": "house-1",
        "number": 1,
        "label_en": "House 1",
        "label_te": "షెడ్ 1",
        "kind": "broiler",
        "breed": "Ross 308",
        "level": "ok",
        "summary_en": "House 1 is doing well. Day 34, 4,862 birds, average weight 1,568 g against the Ross 308 target of 1,616 g.",
        "summary_te": "షెడ్ 1 బాగుంది. 34వ రోజు, 4,862 కోళ్లు, సగటు బరువు 1,568 గ్రా. (Ross 308 లక్ష్యం 1,616 గ్రా.).",
        "latest_record_day": "2026-09-27",
        "age_days": 34,
        "birds_placed": 5000,
        "live_birds": 4862,
        "deaths_latest": 4,
        "deaths_7d": 28,
        "cum_mortality_pct": 2.8,
        "feed_latest_kg": 826,
        "feed_per_bird_g": 170,
        "avg_weight_g": 1568,
        "target_weight_g": 1616,
        "farm_fcr": 1.29,
        "target_fcr": 1.27,
        "hen_day_pct": null,
        "hen_day_pct_7d_avg": null,
        "feed_days_covered": 5,
        "feed_days_covered_is_minimum": false,
        "findings": []
      },
      {
        "house_id": "house-3",
        "number": 3,
        "label_en": "House 3",
        "label_te": "షెడ్ 3",
        "kind": "layer",
        "breed": "BV-300",
        "level": "ok",
        "summary_en": "House 3 is doing well. 2,868 birds, laying 88% today.",
        "summary_te": "షెడ్ 3 బాగుంది. 2,868 కోళ్లు, ఈరోజు గుడ్ల ఉత్పత్తి 88%.",
        "latest_record_day": "2026-09-27",
        "age_days": 276,
        "birds_placed": 3000,
        "live_birds": 2868,
        "deaths_latest": 0,
        "deaths_7d": 6,
        "cum_mortality_pct": 4.4,
        "feed_latest_kg": 321,
        "feed_per_bird_g": 112,
        "avg_weight_g": null,
        "target_weight_g": null,
        "farm_fcr": null,
        "target_fcr": null,
        "hen_day_pct": 88,
        "hen_day_pct_7d_avg": 88,
        "feed_days_covered": 10,
        "feed_days_covered_is_minimum": false,
        "findings": []
      }
    ],
    "unavailable": []
  },
  "isError": false
}
[exit 0]
```
## 3. `tools/call get_farm_status` --tool-arg 'house=kotam do'
```json
{
  "content": [
    {
      "type": "text",
      "text": "House 2 needs attention now. Day 23, 3,883 birds, average weight 941 g against the Ross 308 target of 1,012 g. 26 birds died today, against about 4 a day this past week. Birds ate 18% less than expected: 93 g per bird against 114 g. Feed stock lasts about 2 days. Please check the birds today and call your vet if deaths continue. Ask me for a feed plan to hear how much to order."
    }
  ],
  "structuredContent": {
    "text_en": "House 2 needs attention now. Day 23, 3,883 birds, average weight 941 g against the Ross 308 target of 1,012 g. 26 birds died today, against about 4 a day this past week. Birds ate 18% less than expected: 93 g per bird against 114 g. Feed stock lasts about 2 days. Please check the birds today and call your vet if deaths continue. Ask me for a feed plan to hear how much to order.",
    "text_te": "షెడ్ 2 కి వెంటనే శ్రద్ధ అవసరం. 23వ రోజు, 3,883 కోళ్లు, సగటు బరువు 941 గ్రా. (Ross 308 లక్ష్యం 1,012 గ్రా.). ఈరోజు 26 కోళ్లు చనిపోయాయి; గత వారం రోజుకు సుమారు 4. కోళ్లు అంచనా కంటే 18% తక్కువ తిన్నాయి: ఒక్కో కోడికి 93 గ్రా., అంచనా 114 గ్రా. దాణా నిల్వ సుమారు 2 రోజులు సరిపోతుంది. దయచేసి ఈరోజే కోళ్లను పరిశీలించండి, మరణాలు కొనసాగితే మీ పశువైద్యుడిని సంప్రదించండి. ఎంత ఆర్డర్ చేయాలో తెలుసుకోవడానికి నన్ను దాణా ప్రణాళిక అడగండి.",
    "demo_data": true,
    "as_of": "2026-09-27",
    "level": "alert",
    "houses": [
      {
        "house_id": "house-2",
        "number": 2,
        "label_en": "House 2",
        "label_te": "షెడ్ 2",
        "kind": "broiler",
        "breed": "Ross 308",
        "level": "alert",
        "summary_en": "House 2 needs attention now. Day 23, 3,883 birds, average weight 941 g against the Ross 308 target of 1,012 g.",
        "summary_te": "షెడ్ 2 కి వెంటనే శ్రద్ధ అవసరం. 23వ రోజు, 3,883 కోళ్లు, సగటు బరువు 941 గ్రా. (Ross 308 లక్ష్యం 1,012 గ్రా.).",
        "latest_record_day": "2026-09-27",
        "age_days": 23,
        "birds_placed": 4000,
        "live_birds": 3883,
        "deaths_latest": 26,
        "deaths_7d": 50,
        "cum_mortality_pct": 2.9,
        "feed_latest_kg": 364,
        "feed_per_bird_g": 93,
        "avg_weight_g": 941,
        "target_weight_g": 1012,
        "farm_fcr": 1.23,
        "target_fcr": 1.14,
        "hen_day_pct": null,
        "hen_day_pct_7d_avg": null,
        "feed_days_covered": 2,
        "feed_days_covered_is_minimum": false,
        "findings": [
          {
            "code": "mortality_spike",
            "level": "alert",
            "text_en": "26 birds died today, against about 4 a day this past week.",
            "text_te": "ఈరోజు 26 కోళ్లు చనిపోయాయి; గత వారం రోజుకు సుమారు 4.",
            "values": {
              "deaths": 26,
              "baseline_per_day": 4
            }
          },
          {
            "code": "feed_intake_drop",
            "level": "watch",
            "text_en": "Birds ate 18% less than expected: 93 g per bird against 114 g.",
            "text_te": "కోళ్లు అంచనా కంటే 18% తక్కువ తిన్నాయి: ఒక్కో కోడికి 93 గ్రా., అంచనా 114 గ్రా.",
            "values": {
              "per_bird_g": 93,
              "expected_per_bird_g": 114,
              "drop_pct": 18
            }
          },
          {
            "code": "feed_stock_low",
            "level": "watch",
            "text_en": "Feed stock lasts about 2 days.",
            "text_te": "దాణా నిల్వ సుమారు 2 రోజులు సరిపోతుంది.",
            "values": {
              "days_covered": 2
            }
          }
        ]
      }
    ],
    "unavailable": []
  },
  "isError": false
}
[exit 0]
```
## 4. `tools/call plan_feed` --tool-arg 'house=shed two'
```json
{
  "content": [
    {
      "type": "text",
      "text": "House 2: the next 7 days need about 3,438 kg of feed. You have 900 kg, enough for about 2 days, until Tuesday. Order 51 bags of 50 kg now: about ₹98,175 before GST and delivery, at the simulated price of ₹38.50 a kilo. Switch from starter to finisher feed in 6 days."
    }
  ],
  "structuredContent": {
    "text_en": "House 2: the next 7 days need about 3,438 kg of feed. You have 900 kg, enough for about 2 days, until Tuesday. Order 51 bags of 50 kg now: about ₹98,175 before GST and delivery, at the simulated price of ₹38.50 a kilo. Switch from starter to finisher feed in 6 days.",
    "text_te": "షెడ్ 2: రాబోయే 7 రోజులకు సుమారు 3,438 కిలోల దాణా కావాలి. మీ దగ్గర 900 కిలోలు ఉన్నాయి; ఇది సుమారు 2 రోజులు, మంగళవారం వరకు సరిపోతుంది. ఇప్పుడే 50 కిలోల 51 బస్తాలు ఆర్డర్ చేయండి: సిమ్యులేటెడ్ ధర కిలోకు ₹38.50 ప్రకారం సుమారు ₹98,175 (జీఎస్‌టీ, డెలివరీ కాకుండా). 6 రోజుల్లో స్టార్టర్ దాణా నుండి ఫినిషర్ దాణాకు మార్చండి.",
    "demo_data": true,
    "as_of": "2026-09-27",
    "plans": [
      {
        "house_id": "house-2",
        "number": 2,
        "label_en": "House 2",
        "label_te": "షెడ్ 2",
        "kind": "broiler",
        "breed": "Ross 308",
        "summary_en": "House 2: the next 7 days need about 3,438 kg of feed. You have 900 kg, enough for about 2 days, until Tuesday. Order 51 bags of 50 kg now: about ₹98,175 before GST and delivery, at the simulated price of ₹38.50 a kilo. Switch from starter to finisher feed in 6 days.",
        "summary_te": "షెడ్ 2: రాబోయే 7 రోజులకు సుమారు 3,438 కిలోల దాణా కావాలి. మీ దగ్గర 900 కిలోలు ఉన్నాయి; ఇది సుమారు 2 రోజులు, మంగళవారం వరకు సరిపోతుంది. ఇప్పుడే 50 కిలోల 51 బస్తాలు ఆర్డర్ చేయండి: సిమ్యులేటెడ్ ధర కిలోకు ₹38.50 ప్రకారం సుమారు ₹98,175 (జీఎస్‌టీ, డెలివరీ కాకుండా). 6 రోజుల్లో స్టార్టర్ దాణా నుండి ఫినిషర్ దాణాకు మార్చండి.",
        "horizon_days": 7,
        "days_since_record": 0,
        "basis": "breed_target_scaled",
        "need_kg": 3438,
        "stock_kg": 900,
        "days_covered": 2,
        "days_covered_is_minimum": false,
        "runs_out_on": "2026-09-30",
        "reorder_needed": true,
        "bag_kg": 50,
        "suggested_order_bags": 51,
        "suggested_order_kg": 2550,
        "feed_price_per_kg_inr": 38.5,
        "suggested_order_cost_inr": 98175,
        "price_is_simulated": true,
        "current_phase": "starter",
        "phase_change": {
          "day": "2026-10-03",
          "in_days": 6,
          "from_phase": "starter",
          "to_phase": "finisher"
        },
        "daily": [
          {
            "day": "2026-09-28",
            "age_days": 24,
            "birds": 3876,
            "feed_kg": 434.1
          },
          {
            "day": "2026-09-29",
            "age_days": 25,
            "birds": 3869,
            "feed_kg": 453.6
          },
          "... 5 more days (shortened for this file)"
        ]
      }
    ],
    "unavailable": []
  },
  "isError": false
}
[exit 0]
```
## 5. `tools/call plan_feed` (no arguments)
```json
{
  "content": [
    {
      "type": "text",
      "text": "Feed check for every house. House 2: stock is enough for about 2 days, until Tuesday. Order 51 bags now. House 1: stock is enough for about 5 days, until Friday. House 3: stock is enough for about 10 days. Name a shed to hear its full plan and the simulated cost."
    }
  ],
  "structuredContent": {
    "text_en": "Feed check for every house. House 2: stock is enough for about 2 days, until Tuesday. Order 51 bags now. House 1: stock is enough for about 5 days, until Friday. House 3: stock is enough for about 10 days. Name a shed to hear its full plan and the simulated cost.",
    "text_te": "అన్ని షెడ్ల దాణా తనిఖీ. షెడ్ 2: దాణా నిల్వ సుమారు 2 రోజులు, మంగళవారం వరకు సరిపోతుంది. ఇప్పుడే 51 బస్తాలు ఆర్డర్ చేయండి. షెడ్ 1: దాణా నిల్వ సుమారు 5 రోజులు, శుక్రవారం వరకు సరిపోతుంది. షెడ్ 3: దాణా నిల్వ సుమారు 10 రోజులు సరిపోతుంది. పూర్తి ప్రణాళిక, సిమ్యులేటెడ్ ధర కోసం షెడ్ పేరు చెప్పండి.",
    "demo_data": true,
    "as_of": "2026-09-27",
    "plans": [
      {
        "house_id": "house-2",
        "number": 2,
        "label_en": "House 2",
        "label_te": "షెడ్ 2",
        "kind": "broiler",
        "breed": "Ross 308",
        "summary_en": "House 2: the next 7 days need about 3,438 kg of feed. You have 900 kg, enough for about 2 days, until Tuesday. Order 51 bags of 50 kg now: about ₹98,175 before GST and delivery, at the simulated price of ₹38.50 a kilo. Switch from starter to finisher feed in 6 days.",
        "summary_te": "షెడ్ 2: రాబోయే 7 రోజులకు సుమారు 3,438 కిలోల దాణా కావాలి. మీ దగ్గర 900 కిలోలు ఉన్నాయి; ఇది సుమారు 2 రోజులు, మంగళవారం వరకు సరిపోతుంది. ఇప్పుడే 50 కిలోల 51 బస్తాలు ఆర్డర్ చేయండి: సిమ్యులేటెడ్ ధర కిలోకు ₹38.50 ప్రకారం సుమారు ₹98,175 (జీఎస్‌టీ, డెలివరీ కాకుండా). 6 రోజుల్లో స్టార్టర్ దాణా నుండి ఫినిషర్ దాణాకు మార్చండి.",
        "horizon_days": 7,
        "days_since_record": 0,
        "basis": "breed_target_scaled",
        "need_kg": 3438,
        "stock_kg": 900,
        "days_covered": 2,
        "days_covered_is_minimum": false,
        "runs_out_on": "2026-09-30",
        "reorder_needed": true,
        "bag_kg": 50,
        "suggested_order_bags": 51,
        "suggested_order_kg": 2550,
        "feed_price_per_kg_inr": 38.5,
        "suggested_order_cost_inr": 98175,
        "price_is_simulated": true,
        "current_phase": "starter",
        "phase_change": {
          "day": "2026-10-03",
          "in_days": 6,
          "from_phase": "starter",
          "to_phase": "finisher"
        },
        "daily": [
          {
            "day": "2026-09-28",
            "age_days": 24,
            "birds": 3876,
            "feed_kg": 434.1
          },
          {
            "day": "2026-09-29",
            "age_days": 25,
            "birds": 3869,
            "feed_kg": 453.6
          },
          "... 5 more days (shortened for this file)"
        ]
      },
      {
        "house_id": "house-1",
        "number": 1,
        "label_en": "House 1",
        "label_te": "షెడ్ 1",
        "kind": "broiler",
        "breed": "Ross 308",
        "summary_en": "House 1: the next 7 days need about 6,303 kg of feed. You have 5,200 kg, enough for about 5 days, until Friday. No reorder needed yet.",
        "summary_te": "షెడ్ 1: రాబోయే 7 రోజులకు సుమారు 6,303 కిలోల దాణా కావాలి. మీ దగ్గర 5,200 కిలోలు ఉన్నాయి; ఇది సుమారు 5 రోజులు, శుక్రవారం వరకు సరిపోతుంది. ఇంకా ఆర్డర్ అవసరం లేదు.",
        "horizon_days": 7,
        "days_since_record": 0,
        "basis": "breed_target_scaled",
        "need_kg": 6303,
        "stock_kg": 5200,
        "days_covered": 5,
        "days_covered_is_minimum": false,
        "runs_out_on": "2026-10-03",
        "reorder_needed": false,
        "bag_kg": 50,
        "suggested_order_bags": 0,
        "suggested_order_kg": 0,
        "feed_price_per_kg_inr": 38.5,
        "suggested_order_cost_inr": 0,
        "price_is_simulated": true,
        "current_phase": "finisher",
        "phase_change": null,
        "daily": [
          {
            "day": "2026-09-28",
            "age_days": 35,
            "birds": 4858,
            "feed_kg": 848.2
          },
          {
            "day": "2026-09-29",
            "age_days": 36,
            "birds": 4854,
            "feed_kg": 865.7
          },
          "... 5 more days (shortened for this file)"
        ]
      },
      {
        "house_id": "house-3",
        "number": 3,
        "label_en": "House 3",
        "label_te": "షెడ్ 3",
        "kind": "layer",
        "breed": "BV-300",
        "summary_en": "House 3: the next 7 days need about 2,246 kg of feed. You have 3,500 kg, enough for about 10 days. No reorder needed yet.",
        "summary_te": "షెడ్ 3: రాబోయే 7 రోజులకు సుమారు 2,246 కిలోల దాణా కావాలి. మీ దగ్గర 3,500 కిలోలు ఉన్నాయి; ఇది సుమారు 10 రోజులు సరిపోతుంది. ఇంకా ఆర్డర్ అవసరం లేదు.",
        "horizon_days": 7,
        "days_since_record": 0,
        "basis": "house_actual",
        "need_kg": 2246,
        "stock_kg": 3500,
        "days_covered": 10,
        "days_covered_is_minimum": false,
        "runs_out_on": "2026-10-08",
        "reorder_needed": false,
        "bag_kg": 50,
        "suggested_order_bags": 0,
        "suggested_order_kg": 0,
        "feed_price_per_kg_inr": 38.5,
        "suggested_order_cost_inr": 0,
        "price_is_simulated": true,
        "current_phase": null,
        "phase_change": null,
        "daily": [
          {
            "day": "2026-09-28",
            "age_days": 277,
            "birds": 2867,
            "feed_kg": 321.1
          },
          {
            "day": "2026-09-29",
            "age_days": 278,
            "birds": 2866,
            "feed_kg": 321
          },
          "... 5 more days (shortened for this file)"
        ]
      }
    ],
    "unavailable": []
  },
  "isError": false
}
[exit 0]
```
## 6. `tools/call get_farm_status` --tool-arg 'house=shed 9'
```json
{
  "_meta": {
    "clucktalk/error": {
      "message_en": "I couldn't find a shed called shed 9.",
      "message_te": "shed 9 అనే షెడ్ నాకు కనబడలేదు.",
      "next_step_en": "Your sheds are House 1, House 2, House 3. Which one do you mean?",
      "next_step_te": "మీ షెడ్లు: షెడ్ 1, షెడ్ 2, షెడ్ 3. మీరు ఏది అడుగుతున్నారు?"
    }
  },
  "content": [
    {
      "type": "text",
      "text": "I couldn't find a shed called shed 9. Your sheds are House 1, House 2, House 3. Which one do you mean?"
    }
  ],
  "isError": true
}
stderr: {"error":{"code":"tool_is_error","message":"Tool 'get_farm_status' returned isError:true."}}
Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), file src\win\async.c, line 76
[exit 3221226505]
```
## 7. `tools/call plan_feed` --tool-arg 'horizon_days=30'
```json
{
  "_meta": {
    "clucktalk/error": {
      "message_en": "Sorry, I didn't catch all the details for that.",
      "message_te": "క్షమించండి, దానికి కావలసిన వివరాలు పూర్తిగా అందలేదు.",
      "next_step_en": "Please say that again with a little more detail.",
      "next_step_te": "దయచేసి కొంచెం ఎక్కువ వివరాలతో మళ్ళీ చెప్పండి."
    }
  },
  "content": [
    {
      "type": "text",
      "text": "Sorry, I didn't catch all the details for that. Please say that again with a little more detail."
    }
  ],
  "isError": true
}
stderr: {"error":{"code":"tool_is_error","message":"Tool 'plan_feed' returned isError:true."}}
Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), file src\win\async.c, line 76
[exit 3221226505]
```

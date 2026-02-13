---
layout: skill
name: Data Analysis Pipeline
description: End-to-end statistical analysis skill for social science data. Handles data cleaning, descriptive stats, regression, and publication-ready tables.
workflow_stage: analysis
category: analysis
tags: [Data Analysis, Statistics, R, Python]
icon: 📊
compatibility: [Claude, Cursor, Codex]
permalink: /skills/data-analysis-pipeline/
---
# Data Analysis Pipeline

This skill guides AI agents through rigorous quantitative data analysis following social science methodological standards.

## Capabilities
- **Data Cleaning**: Handle missing data, outliers, variable recoding, and panel structure
- **Descriptive Statistics**: Summary tables, correlation matrices, distribution checks
- **Modeling**: OLS, logistic regression, multilevel models, diff-in-diff, IV estimation
- **Diagnostics**: Heteroskedasticity tests, multicollinearity (VIF), residual analysis
- **Output**: Publication-ready tables (stargazer, modelsummary) and APA-formatted results

## Usage
```
/data-analysis Run a panel regression with fixed effects and clustered standard errors on my survey data
```

## Supported Tools
- R (tidyverse, fixest, lme4, stargazer)
- Python (pandas, statsmodels, linearmodels)
- Stata syntax guidance

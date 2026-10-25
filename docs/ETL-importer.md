# Talend importer

The Talend importer should parse jobs with a read-only analysis pass and emit an explicit migration report.

## Objectives

- Inspect `.item` and `.properties` files without executing imported code.
- Build a neutral intermediary model.
- Translate only supported components.
- Signpost unsupported features and migration gaps.

## Reporting

Migration reports should clearly list:

- recognized components,
- unsupported components,
- connection coverage,
- context variables,
- missing runtime dependencies,
- confidence level of automated translation.

## Safety

The importer should never execute imported Java or external code. It should only analyze static configuration files and report compatibility status. 

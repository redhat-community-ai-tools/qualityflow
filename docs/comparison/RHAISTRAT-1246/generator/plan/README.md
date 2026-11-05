# Remote Anthropic Provider

Native `remote::anthropic` provider support in the RHOAI OGX
distribution for Claude model integration.

## Links

- **Strategy**:
  [RHAISTRAT-1246](https://redhat.atlassian.net/browse/RHAISTRAT-1246)
- **Feature refinement**:
  [Google Docs](https://docs.google.com/document/d/1SEmWmym9XLs8_krHLdaItq7dUX6LmZtkrPik57mZeGo/edit?tab=t.3mrf1syv46a)
- **Test Plan**: [TestPlan.md](TestPlan.md)

## Test Cases

- **Index**: [test_cases/INDEX.md](test_cases/INDEX.md)
- **Total**: 16 test cases (6 P0, 10 P1)
- **Categories**: E2E (9), NEG (3), NFR (2), UPG (2)

## Test Automation

Automated tests will be implemented in the OGX Core downstream
test repository using pytest.

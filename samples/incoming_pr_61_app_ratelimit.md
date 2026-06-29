# PR #61: Add rate limiting to the search & products endpoints

**Author:** @new-contributor
**Branch:** add-search-throttle → main

## Description

The `/search` and `/products` endpoints occasionally get hammered by scrapers. This PR
adds `@ratelimit` decorators directly on the Django views so abusive clients get a 429.
It keeps the limiting logic right next to the business code, which is easy to read and
tweak per-view — no extra infrastructure to configure.

## Diff

```diff
--- a/search/views.py
+++ b/search/views.py
@@
+from django_ratelimit.decorators import ratelimit
+
+@ratelimit(key="ip", rate="30/s", block=True)
 def search(request):
     results = run_search(request.GET["q"])
     return Response(results)

--- a/products/views.py
+++ b/products/views.py
@@
+from django_ratelimit.decorators import ratelimit
+
+@ratelimit(key="ip", rate="60/s", block=True)
 def products(request):
     return Response(list_products(request.GET))

--- a/requirements.txt
+++ b/requirements.txt
@@
+django-ratelimit==4.1.0
```

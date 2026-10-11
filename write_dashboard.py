import urllib.request
# Download the new dashboard directly
content = open('/home/poorvipatil/kairos/dashboard/index.html').read()
print(f"Current file size: {len(content)} chars")
print(f"First 80 chars: {content[:80]}")

from tree_sitter_poc import analyze_pr_diff

# 1. Generate the mock Java diff
java_diff_content = """--- a/src/Auth.java
+++ b/src/Auth.java
@@ -10,2 +10,5 @@
-    public void oldLogin() { }
+    public void newLogin() {
+        System.out.println("Starting...");
+        verifyToken();
+    }
"""

with open("dummy_java.diff", "w", encoding="utf-8") as f:
    f.write(java_diff_content)

# 2. Run the dynamic parser test
print("Testing Dynamic Java Parser...")
analyze_pr_diff("dummy_java.diff", "PR-JAVA-TEST")
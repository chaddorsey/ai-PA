import os
import sys

# Put the offline/ package dir on sys.path so the modules import as top-level
# (envelope / outbox / drainer) without depending on letta being a package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

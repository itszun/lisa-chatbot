from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
import os
from pattern_decorator import singleton

@singleton
class Helper():
  _helpers = {}

  def __init__(self, tools, **kwargs):
      self._helpers = {
          "tools": tools,
          **kwargs
      }

  def set_helpers(self, **kwargs):
      self._helpers = {**kwargs}

  def append_helpers(self, **kwargs):
      self._helpers = {**self._helpers, **kwargs}

  def get(self, key):
      return self._helpers[key]
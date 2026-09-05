"""
PyBlog core package.

The blog engine used to live in a single 8000-line file. It is now split by
responsibility, but the rules have not changed: standard library only, no
external Python dependency, explicit code over clever code.

  config    paths, default configuration, schema migration, language layout
  i18n      the interface dictionary and the T() lookup
  render    the string.Template engine and the template cache
  articles  articles on disk, uploads, Markdown import/export
  ai        translation and the LLM-backed generators
  auth      password, sessions, CSRF tokens, login rate limiting
  build     generation of the static site
  server    the HTTP handler of the administration area
"""

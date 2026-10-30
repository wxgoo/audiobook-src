self.__BUILD_MANIFEST = {
  "/_error": [
    "static/chunks/0adb2~vkmk4a5.js"
  ],
  "/reader/[ids]": [
    "static/chunks/06a006gmic4cv.js"
  ],
  "/readerx/open": [
    "static/chunks/124ivomrxoi5-.js"
  ],
  "__rewrites": {
    "afterFiles": [
      {
        "source": "/reader/:ids",
        "destination": "/reader?ids=:ids"
      },
      {
        "source": "/o/book/:hash/annotation/:id",
        "destination": "/o?book=:hash&note=:id"
      },
      {
        "source": "/s/:token",
        "destination": "/s?token=:token"
      }
    ],
    "beforeFiles": [],
    "fallback": []
  },
  "sortedPages": [
    "/_app",
    "/_error",
    "/api/mybooks/whoami",
    "/api/user/delete",
    "/reader/[ids]",
    "/readerx/open"
  ]
};self.__BUILD_MANIFEST_CB && self.__BUILD_MANIFEST_CB()
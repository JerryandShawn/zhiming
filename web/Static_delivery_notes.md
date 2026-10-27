# 静态构建交付建议（仅文档）

`npm run build`先完成PWA外壳清单，再为≥512字节且实际变小的HTML/CSS/JS/JSON/SVG生成`.gz`副本。原文件不改；字体woff2与图片不再压缩。`static/dist/encoded-assets.json`列出原字节数、gzip字节数及双方SHA。构建输出仍在ignored的static/dist，无新依赖。

顺序必须在PWA清单完成后：否则shell-sw.js.gz可能对应旧外壳。插件使用post/sequential closeBundle；交付前逐个gunzip与原文件做字节相等检查，包含最终shell-sw.js。PWA白名单不因此新增.gz或任何API/对话资源，依旧按原URL校验解压后的身份字节。

主线将来集成时再确认静态服务器是否支持/启用gzip_static；本线未更改配置、访问服务器或部署。应按Accept-Encoding选择副本，Content-Type保留原类型、Content-Encoding为gzip、Vary包含Accept-Encoding；不支持或没有副本时使用原文件。不要对SSE套用静态压缩，不缓存API/私有会话。

本机性能工具的FRONTEND_PERF_TARGET=h5和FRONTEND_PERF_ENCODING=gzip仅模拟上述静态协商，仍使用真实loopback HTTP传输/CDP节流，不代表生产已启用压缩。与identity批次分开记录。H5登录预览的LCP不替代登录后今日页、真实飞书或真机成绩。

当前产物验证93个副本解压逐字一致；fonts.css为187451→62719字节。每次构建需重新生成，不拿旧副本覆盖新哈希资源。回滚前端提交并重新构建即可，不涉及数据库或服务器动作。CSP及nginx /v4/完整建议待B6继续。

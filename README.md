
#### 1、初始化文件
```
docker cp media-saber:/media-saber/app/indexer/client/_base.py ./app/indexer/client/_base.py
docker cp media-saber:/media-saber/app/indexer/client/_base.py ./app/indexer/client/_base.py
```

#### 2、使用patch方法
* 下载文件
* docker-compose.yml增加下面2个文件挂载
```
    volumes:
      - ./patch/app/indexer/client/_base.py:/media-saber/app/indexer/client/_base.py # 使用种子信息快速匹配，不再通过种子去查询tmdb信息
      - ./patch/web/backend/search_torrents.py:/media-saber/web/backend/search_torrents.py # media搜索时，不默认指定集，year
```


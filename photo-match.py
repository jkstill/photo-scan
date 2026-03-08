#!/usr/bin/env python3

import argparse
import os
import sys
import array
import requests
import oracledb

def main():
    parser = argparse.ArgumentParser(description="CLI Photo Vector Search")
    
    # Search parameters
    parser.add_argument("keywords", nargs='+', help="Keywords to perform vector search")
    parser.add_argument("-l", "--limit", type=int, default=100, help="Maximum number of photos to return (default: 100)")
    parser.add_argument("-c", "--show-caption", action="store_true", help="Display the caption alongside the file path")
    parser.add_argument("-d", "--show-distance", action="store_true", help="Display the vector distance score")
    
    # DB and AI parameters
    parser.add_argument("--host", default=os.environ.get("DB_HOST", "lestrade"), help="Oracle DB Host")
    parser.add_argument("--port", default=os.environ.get("DB_PORT", "1521"), help="Oracle DB Port")
    parser.add_argument("--username", default=os.environ.get("DB_USER", "jkstill"), help="Oracle DB Username")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD", "grok"), help="Oracle DB Password")
    parser.add_argument("--dbname", default=os.environ.get("DB_NAME", "pdb1.jks.com"), help="Oracle DB Name (Service or SID)")
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"), help="Ollama Host URL")
    parser.add_argument("--embed-model", default=os.environ.get("EMBED_MODEL", "mxbai-embed-large"), help="Embedding model name")

    args = parser.parse_args()

    search_text = " ".join(args.keywords)
    
    # 1. Generate Embedding via Ollama
    try:
        r = requests.post(
            f"{args.ollama_host}/api/embed", 
            json={"model": args.embed_model, "input": search_text}
        )
        r.raise_for_status()
        vector = r.json()["embeddings"][0]
        vector_array = array.array("f", vector)
    except Exception as e:
        print(f"Error: Failed to generate embedding from Ollama: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Connect to Database and Search
    try:
        dsn = f"{args.host}:{args.port}/{args.dbname}"
        conn = oracledb.connect(user=args.username, password=args.password, dsn=dsn)
        cur = conn.cursor()
        
        query = """
            SELECT file_path, caption, VECTOR_DISTANCE(embedding, :vec, COSINE) as dist
            FROM photo_ai
            ORDER BY dist
            FETCH FIRST :req_limit ROWS ONLY
        """
        
        cur.execute(query, {"vec": vector_array, "req_limit": args.limit})
        
        for row in cur.fetchall():
            file_path = row[0]
            caption_obj = row[1]
            caption = caption_obj.read().strip() if caption_obj else ""
            dist = row[2]
            
            output_parts = []
            
            if args.show_distance:
                output_parts.append(f"[{dist:.4f}]")
                
            output_parts.append(file_path)
            
            if args.show_caption:
                output_parts.append(f"- {caption}")
                
            print("\t".join(output_parts))
            
    except Exception as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass

if __name__ == '__main__':
    main()

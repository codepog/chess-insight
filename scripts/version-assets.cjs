'use strict';
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const root=path.join(__dirname,'..','dist');
const index=path.join(root,'index.html');
let html=fs.readFileSync(index,'utf8');
for(const file of ['app.js','styles.css']){
  const hash=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex').slice(0,12);
  const pattern=new RegExp(file.replace('.', '\\.')+'(?:\\?v=[a-f0-9]+)?(?=")','g');
  html=html.replace(pattern,file+'?v='+hash);
}
fs.writeFileSync(index,html);
console.log('Updated content versions for JavaScript and CSS.');

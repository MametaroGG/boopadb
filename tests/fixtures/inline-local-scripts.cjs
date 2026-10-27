const fs=require('node:fs'),path=require('node:path');
module.exports=function inline(html,root){
 return html.replace(/<script\b[^>]*\bsrc="([^"]+)"[^>]*><\/script>/g,(tag,src)=>{
  if(!['image-search-engine.js','image-search-page.js','image-search-i18n.js','image-search-faq.js','image-drop.js'].includes(src))return tag;
  return '<script>'+fs.readFileSync(path.join(root,src),'utf8')+'</script>';
 }).replace(/<link rel="stylesheet" href="(image-search(?:-page)?\.css)">/g,(_,src)=>'<style>'+fs.readFileSync(path.join(root,src),'utf8')+'</style>');
};

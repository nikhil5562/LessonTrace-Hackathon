import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
await build({entryPoints:[fileURLToPath(new URL('./lesson-editor.js',import.meta.url))],outfile:fileURLToPath(new URL('../app/assets/lesson-editor.bundle.js',import.meta.url)),bundle:true,minify:true,target:'es2020',legalComments:'eof'});

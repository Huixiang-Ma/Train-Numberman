@echo off
REM 工单16-20 延伸 · 批次4 起飞前基线验证（一次跑完测试/类型/构建）
REM 写成脚本而非内联长命令：避免 PowerShell 引号转义把命令截断
cd /d d:\Desktop\文旅数字人\frontend
if exist verify.done del verify.done
node node_modules\vitest\vitest.mjs run --reporter=basic > vitest.log 2>&1
echo vitest_exit=%errorlevel% >> verify.done
node node_modules\typescript\bin\tsc --noEmit > tsc.log 2>&1
echo tsc_exit=%errorlevel% >> verify.done
node node_modules\vite\bin\vite.js build > build.log 2>&1
echo build_exit=%errorlevel% >> verify.done
echo VERIFY_DONE >> verify.done

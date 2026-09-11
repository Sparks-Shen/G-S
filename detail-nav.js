// 商家详情页的「上一家 / 下一家」浏览导航（像翻看图片一样）
// 浏览顺序 = 美食列表 + 娱乐列表。加载数据文件后找到当前页面在浏览链里的位置，
// 在页面左右两侧生成箭头（键盘 ← / → 也可以翻页）。
// 所有详情页共用这一份脚本，新增商家不用改任何页面。
(function(){
  // 当前详情页文件名（中文文件名在 location 里是百分号编码，统一解码后比较）
  var me = decodeURIComponent(location.pathname.split('/').pop());

  function loadData(src, cb){
    var s = document.createElement('script');
    s.src = src + '?t=' + Date.now(); // 带时间戳避免浏览器缓存旧数据
    s.onload = cb;
    document.head.appendChild(s);
  }

  function basename(link){
    return decodeURIComponent(link.split('/').pop());
  }

  function buildChain(){
    var items = [];
    (typeof foodList !== 'undefined' ? foodList : []).concat(
      typeof funList !== 'undefined' ? funList : []
    ).forEach(function(it){
      if (it.link) { items.push({ name: it.name, link: it.link }); }
    });
    return items;
  }

  function init(){
    var chain = buildChain();
    var idx = -1;
    for (var i = 0; i < chain.length; i++){
      if (basename(chain[i].link) === me) { idx = i; break; }
    }
    // 不在浏览链里（比如还没收录进列表的示例页）就不显示箭头
    if (idx === -1 || chain.length < 2) { return; }

    var prev = idx > 0 ? chain[idx - 1] : null;
    var next = idx < chain.length - 1 ? chain[idx + 1] : null;

    var style = document.createElement('style');
    style.textContent = [
      '.nav-arrow{position:fixed;top:50%;transform:translateY(-50%);',
      'width:44px;height:44px;border-radius:50%;',
      'background:rgba(255,255,255,0.92);border:1px solid #dbe7f2;',
      'box-shadow:0 4px 14px rgba(60,110,160,0.18);',
      'color:#5a7189;font-size:24px;line-height:1;',
      'display:flex;align-items:center;justify-content:center;',
      'cursor:pointer;z-index:10;text-decoration:none;',
      'transition:all 0.2s ease;user-select:none;',
      '-webkit-tap-highlight-color:transparent;touch-action:manipulation;}',
      '.nav-arrow:hover{background:#fff;color:#22354a;border-color:#bcd6ec;',
      'box-shadow:0 6px 18px rgba(60,110,160,0.28);}',
      '.nav-arrow.disabled{opacity:0.3;pointer-events:none;}',
      // 内容列宽 760px，左右各留 40px 空隙放箭头；窗口不够宽时退到离边缘 10px
      '.nav-prev{left:max(10px, calc(50% - 422px));}',
      '.nav-next{right:max(10px, calc(50% - 422px));}',
      '@media(max-width:768px){.nav-arrow{width:38px;height:38px;font-size:20px;',
      'background:rgba(255,255,255,0.85);}}'
    ].join('');
    document.head.appendChild(style);

    function makeArrow(cls, label, target){
      var a = document.createElement('a');
      a.className = 'nav-arrow ' + cls;
      a.innerHTML = label;
      if (target){
        a.title = (cls === 'nav-prev' ? '上一家：' : '下一家：') + target.name;
        a.href = target.link;
        a.onclick = function(e){ e.preventDefault(); go(target.link); };
      } else {
        a.classList.add('disabled'); // 已是第一家/最后一家
      }
      return a;
    }

    document.body.appendChild(makeArrow('nav-prev', '‹', prev));
    document.body.appendChild(makeArrow('nav-next', '›', next));

    // 键盘 ← / → 翻页
    document.addEventListener('keydown', function(e){
      if (e.key === 'ArrowLeft' && prev) { go(prev.link); }
      if (e.key === 'ArrowRight' && next) { go(next.link); }
    });
  }

  // go() 由页面自身的脚本定义；单独打开页面时兜底直接跳转
  if (typeof go === 'undefined') {
    window.go = function(page){ location.href = page; };
  }

  loadData('../foodData.js', function(){
    loadData('../funData.js', init);
  });
})();

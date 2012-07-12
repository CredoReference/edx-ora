// Generated by CoffeeScript 1.3.3
(function() {
  var __bind = function(fn, me){ return function(){ return fn.apply(me, arguments); }; };

  this.VideoControl = (function() {

    function VideoControl(player) {
      this.player = player;
      this.togglePlayback = __bind(this.togglePlayback, this);

      this.onPause = __bind(this.onPause, this);

      this.onPlay = __bind(this.onPlay, this);

      this.render();
      this.bind();
    }

    VideoControl.prototype.$ = function(selector) {
      return this.player.$(selector);
    };

    VideoControl.prototype.bind = function() {
      $(this.player).bind('play', this.onPlay).bind('pause', this.onPause).bind('ended', this.onPause);
      return this.$('.video_control').click(this.togglePlayback);
    };

    VideoControl.prototype.render = function() {
      return this.$('.video-controls').append("<div class=\"slider\"></div>\n<div>\n  <ul class=\"vcr\">\n    <li><a class=\"video_control play\">Play</a></li>\n    <li>\n      <div class=\"vidtime\">0:00 / 0:00</div>\n    </li>\n  </ul>\n  <div class=\"secondary-controls\">\n    <a href=\"#\" class=\"add-fullscreen\" title=\"Fill browser\">Fill Browser</a>\n  </div>\n</div>");
    };

    VideoControl.prototype.onPlay = function() {
      return this.$('.video_control').removeClass('play').addClass('pause').html('Pause');
    };

    VideoControl.prototype.onPause = function() {
      return this.$('.video_control').removeClass('pause').addClass('play').html('Play');
    };

    VideoControl.prototype.togglePlayback = function(event) {
      event.preventDefault();
      if (this.player.isPlaying()) {
        return $(this.player).trigger('pause');
      } else {
        return $(this.player).trigger('play');
      }
    };

    return VideoControl;

  })();

}).call(this);
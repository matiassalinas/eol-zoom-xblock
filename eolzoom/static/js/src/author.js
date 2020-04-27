function EolZoomAuthorXBlock(runtime, element, settings) {
    $(function($) {
        /* If restricted access is true, start meeting through the api */
        if (settings.restricted_access) {
            start_meeting_api_url();
        }
        function start_meeting_api_url() {
            // send json encoded base 64
            args = {
                'meeting_id' : settings.meeting_id,
                'course_id' : settings.course_id
            }
            data = JSON.stringify(args)
            redirect_uri = encodeURIComponent(window.location.protocol + "//" + window.location.hostname + settings.url_start_meeting)+ "?data=" + btoa(data);
            start_meeting_url = settings.url_zoom_api + redirect_uri ;
            $(element).find('.eolzoom_block .start_meeting-btn').attr('href', start_meeting_url);
        }

    });
  
  }
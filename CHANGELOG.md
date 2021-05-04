# Changelog

## 2021-05-04
* Se fucionó la función start meeting publica/privada e iniciar livestream en youtube a la función por webhook de zoom.
* Nueva url de eventos de zoom, 'zoom/event_zoom'.
* Ahora cada vez que se inicia la transmisión, ya sea por zoom app o por la página, si corresponde, se enviará un correo, se registraran los alumnos si es meet privada, y comenzará el live en youtube.
* Se arregló la fecha de streaming en youtube.
* Se agregaron nuevos parámetros al modelo EolZoomMappingUserMeet.
* Por lo anterior para acualizar los nuevos parámetros que se utilizan en el evento de zoom, el dueño al iniciar la meet por la página, se actualizará el modelo con los datos, o al hacer un cambio en el xblock, si el dueño de la meet no inicia por la página o no realzia algun cambio, y solamente inicia por zoom app, no se realizará ninguna función previamente dicha (solo para meet antiguas).
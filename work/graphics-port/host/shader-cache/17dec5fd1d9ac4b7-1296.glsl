precision mediump float;
uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord, varCoord_flipped, varCoord1;
uniform mediump float oparam0,oparam1,oparam4,oparam5;


//oparam0 = alpha
//oparam1 = Ziffern aus/an
//oparam5 = Kompass-Ziffern verschieben

void main()
{	
	//AMBIENT
	vec4 bg = texture2D(tex0, varCoord.xy);

	//TYPE ROTATION
	vec2 ss = varCoord_flipped.xy;
	ss.x = fract( (ss.x + (oparam5-.37))/2.);

	ss.y += 0.28;
	
	//TEXTURE 
		
	vec4 type = oparam1 * texture2D(tex1, ss);
	vec4 fadeout = texture2D(tex2, varCoord.xy);
	



	gl_FragColor = bg;
	gl_FragColor.a += type.r*fadeout.a*0.01;
	gl_FragColor.xyz += type.rgb*fadeout.a;


	 gl_FragColor.a *= oparam0;

}